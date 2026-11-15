"""HTTP helpers for bank sites that block cloud-hosted scraper traffic."""

import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests


_TRANSLATE_QUERY = {
    "_x_tr_sl": "auto",
    "_x_tr_tl": "en",
    "_x_tr_hl": "en",
}

_BLOCK_PAGE_MARKERS = (
    "request blocked",
    "the request could not be satisfied",
    "access denied",
)


def google_translate_url(url):
    """Return Google's website-translation URL for a public HTTPS page."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only absolute HTTPS URLs can use the translation fallback")

    proxy_host = parsed.hostname.replace("-", "--").replace(".", "-") + ".translate.goog"
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if key not in _TRANSLATE_QUERY]
    query.extend(_TRANSLATE_QUERY.items())
    return urlunsplit(
        ("https", proxy_host, parsed.path or "/", urlencode(query), "")
    )


def _is_block_page(response):
    if response.status_code in (401, 403, 429):
        return True

    content_type = response.headers.get("Content-Type", "")
    if "text" not in content_type and "html" not in content_type:
        return False

    body_start = response.text[:4000].lower()
    return any(marker in body_start for marker in _BLOCK_PAGE_MARKERS)


def _get_with_retry(url, headers, timeout, logger, bank_name, proxy=False):
    """Retry temporary server/proxy failures once, with a bounded delay."""
    retry_statuses = {408, 429, 500, 502, 503, 504}
    if proxy:
        # Translate intermittently returns 400/403 for otherwise valid resources.
        retry_statuses.update({400, 403})
    for attempt in range(2):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code not in retry_statuses or attempt == 1:
                return response
        except requests.RequestException:
            if attempt == 1:
                raise
        logger.warning(f"  ⚠️ {bank_name} temporary HTTP failure; retrying once")
        time.sleep(1)


def get_bank_response(url, headers, logger, bank_name, timeout=20):
    """Fetch a bank resource directly, then retry through Google on WAF blocks.

    The fallback is only used when the direct request fails or returns a known
    block page. The returned boolean records whether the fallback was needed.
    """
    direct_error = None
    parsed = urlsplit(url)
    request_headers = dict(headers)
    request_headers.setdefault("Referer", f"{parsed.scheme}://{parsed.netloc}/")

    try:
        response = _get_with_retry(url, request_headers, timeout, logger, bank_name)
        if not _is_block_page(response):
            response.raise_for_status()
            return response, False

        direct_error = f"HTTP {response.status_code} block page"
    except requests.RequestException as exc:
        direct_error = str(exc)

    fallback_url = google_translate_url(url)
    logger.warning(
        f"  ⚠️ {bank_name} direct request unavailable ({direct_error}); "
        "retrying through the Google Translate web proxy"
    )

    response = _get_with_retry(
        fallback_url, request_headers, timeout, logger, bank_name, proxy=True
    )
    response.raise_for_status()
    if _is_block_page(response):
        raise requests.HTTPError(
            f"{bank_name} fallback returned a block page", response=response
        )

    logger.info(f"  ✅ {bank_name} fallback page retrieved")
    return response, True
