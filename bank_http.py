"""HTTP helpers for bank sites that block cloud-hosted scraper traffic."""

from urllib.parse import urlencode, urlsplit, urlunsplit

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

    proxy_host = parsed.hostname.replace(".", "-") + ".translate.goog"
    return urlunsplit(
        ("https", proxy_host, parsed.path or "/", urlencode(_TRANSLATE_QUERY), "")
    )


def _is_block_page(response):
    if response.status_code in (401, 403, 429):
        return True

    content_type = response.headers.get("Content-Type", "")
    if "text" not in content_type and "html" not in content_type:
        return False

    body_start = response.text[:4000].lower()
    return any(marker in body_start for marker in _BLOCK_PAGE_MARKERS)


def get_bank_response(url, headers, logger, bank_name, timeout=20):
    """Fetch a bank resource directly, then retry through Google on WAF blocks.

    The fallback is only used when the direct request fails or returns a known
    block page. The returned boolean records whether the fallback was needed.
    """
    direct_error = None

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
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

    response = requests.get(fallback_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    if _is_block_page(response):
        raise requests.HTTPError(
            f"{bank_name} fallback returned a block page", response=response
        )

    logger.info(f"  ✅ {bank_name} fallback page retrieved")
    return response, True
