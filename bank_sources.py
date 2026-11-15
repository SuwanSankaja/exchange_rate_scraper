"""Shared readers for BOC, Commercial Bank, and CBSL's public rate sources."""

from datetime import datetime
import math
import re

from bs4 import BeautifulSoup

from bank_http import get_bank_response


EXPECTED_BANKS = (
    'Bank of Ceylon', 'Commercial Bank', 'Amana Bank', "People's Bank",
    'Hatton National Bank', 'Nations Trust Bank', 'Sampath Bank',
    'Central Bank of Sri Lanka',
)

_COMBANK_NAMES = {
    'USD': 'US DOLLARS', 'AUD': 'AUSTRALIAN DOLLARS',
    'EUR': 'EURO', 'GBP': 'STERLING POUNDS',
}


def _rate_pair(buy, sell):
    """Reject missing, nonnumeric, zero, or inverted quotes."""
    buy, sell = (float(str(value).replace(',', '').strip()) for value in (buy, sell))
    if not all(math.isfinite(value) for value in (buy, sell)) or not 0 < buy <= sell:
        raise ValueError('Invalid buying/selling rate pair')
    return buy, sell


def _result(bank, currency, pair, source, url):
    return {
        'bank': bank, 'currency': currency,
        'buying_rate': pair[0], 'selling_rate': pair[1],
        'source': source, 'source_url': url,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


def parse_exchange_table(html, currency_name, selector='table'):
    """Read the currency-note pair; ignore deposit/fee tables on rates pages.

    Both banks put currency notes before drafts/cheques and TT quotes. Keep
    that pair consistent with the existing Commercial Bank API fields.
    """
    soup = BeautifulSoup(html, 'html.parser')
    for table in soup.select(selector):
        text = table.get_text(' ', strip=True).lower()
        if 'buying' not in text or 'selling' not in text:
            continue
        for row in table.select('tr'):
            cells = row.find_all(['td', 'th'], recursive=False)
            if len(cells) < 3:
                continue
            name = ' '.join(cells[0].get_text(' ', strip=True).split()).upper()
            if name == currency_name.upper():
                return _rate_pair(*(cell.get_text(' ', strip=True) for cell in cells[1:3]))
    raise ValueError(f'{currency_name} missing from published exchange-rate table')


def scrape_boc_rates(currency, headers, logger):
    url = 'https://www.boc.lk/rates-tariff'
    try:
        response, fallback = get_bank_response(url, headers, logger, 'BOC')
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.select_one('#exchange-rates table')
        if table is not None and not table.select('tbody td'):
            raise ValueError('BOC is publishing an empty exchange-rate table; bank rates unavailable')
        selector = '#exchange-rates table' if table is not None else 'table'
        pair = parse_exchange_table(response.content, currency, selector)
        source = 'BOC via Google Translate' if fallback else 'BOC Direct'
        return _result('Bank of Ceylon', currency, pair, source, url)
    except Exception as exc:
        logger.warning(f'  ⚠️ BOC {currency} unavailable: {exc}')
        return None


def scrape_combank_rates(currency, headers, logger):
    api_url = 'https://www.combank.lk/api/exchange-rates/'
    try:
        response, fallback = get_bank_response(api_url, headers, logger, 'Commercial Bank')
        rates = response.json()
        if not isinstance(rates, list):
            raise ValueError('Unexpected Commercial Bank API response')
        for rate in rates:
            if rate.get('excode') == currency:
                pair = _rate_pair(rate['currency_buying_rate'], rate['currency_selling_rate'])
                source = 'Combank API via Google Translate' if fallback else 'Combank API'
                return _result('Commercial Bank', currency, pair, source, api_url)
        raise ValueError(f'{currency} missing from Commercial Bank API')
    except Exception as exc:
        logger.warning(f'  ⚠️ Commercial Bank API unavailable ({exc}); trying published rates table')

    url = 'https://www.combank.lk/rates-tariff'
    try:
        response, fallback = get_bank_response(url, headers, logger, 'Commercial Bank rates page')
        pair = parse_exchange_table(response.content, _COMBANK_NAMES[currency])
        source = 'Combank table via Google Translate' if fallback else 'Combank table'
        return _result('Commercial Bank', currency, pair, source, url)
    except Exception as exc:
        logger.error(f'  ❌ Commercial Bank {currency} unavailable: {exc}')
        return None


def parse_cbsl_rates(html):
    soup = BeautifulSoup(html, 'html.parser')
    rates = {}
    for paragraph in soup.select('p'):
        text = paragraph.get_text(' ', strip=True)
        match = re.match(r'^(Buy|Sell)\s*:?[\s\u00a0]*([\d,]+(?:\.\d+)?)\b', text, re.I)
        if match:
            rates[match[1].lower()] = match[2]
    return _rate_pair(rates['buy'], rates['sell'])


def scrape_cbsl_rates(currency, headers, logger):
    url = f'https://www.cbsl.gov.lk/cbsl_custom/charts/{currency.lower()}/indexsmall.php'
    try:
        response, fallback = get_bank_response(url, headers, logger, 'CBSL')
        pair = parse_cbsl_rates(response.content)
        source = 'CBSL via Google Translate' if fallback else 'CBSL Direct'
        return _result('Central Bank of Sri Lanka', currency, pair, source, url)
    except Exception as exc:
        logger.error(f'  ❌ CBSL {currency} unavailable: {exc}')
        return None
