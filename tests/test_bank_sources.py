"""Offline regressions for rate selection, source outages, and HTTP fallback."""

import importlib
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests

import bank_http
import bank_sources


LOGGER = logging.getLogger('test-banks')
LOGGER.addHandler(logging.NullHandler())
CURRENCIES = ('AUD', 'USD', 'EUR', 'GBP')


def response(body, status=200, content_type='text/html'):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode()
    result.headers['Content-Type'] = content_type
    result.url = 'https://bank.example/rates'
    return result


def table(rows):
    return ('<table><thead><tr><th>Currency</th><th>Buying Rate</th>'
            '<th>Selling Rate</th></tr></thead><tbody>' + rows + '</tbody></table>')


class HttpTests(unittest.TestCase):
    def test_translation_preserves_query_and_escapes_hostname(self):
        url = bank_http.google_translate_url('https://my-bank.example/rates?date=2026-11-13&empty=')
        self.assertEqual(urlsplit(url).hostname, 'my--bank-example.translate.goog')
        self.assertEqual(parse_qs(urlsplit(url).query)['date'], ['2026-11-13'])
        self.assertIn('empty=', url)
        with self.assertRaises(ValueError):
            bank_http.google_translate_url('http://bank.example/rates')

    @patch('bank_http.requests.get')
    def test_direct_request_supplies_referrer_without_mutating_headers(self, get):
        get.return_value = response('rates')
        headers = {'User-Agent': 'test'}
        result, fallback = bank_http.get_bank_response('https://bank.example/rates', headers, LOGGER, 'bank')
        self.assertFalse(fallback)
        self.assertEqual(result.text, 'rates')
        self.assertEqual(get.call_args.kwargs['headers']['Referer'], 'https://bank.example/')
        self.assertNotIn('Referer', headers)

    @patch('bank_http.time.sleep')
    @patch('bank_http.requests.get')
    def test_blocked_direct_and_transient_proxy_400_recover(self, get, sleep):
        get.side_effect = [response('blocked', 403), response('Cannot translate', 400), response('rates')]
        result, fallback = bank_http.get_bank_response('https://bank.example/rates', {}, LOGGER, 'bank')
        self.assertTrue(fallback)
        self.assertEqual(result.text, 'rates')
        self.assertEqual(get.call_count, 3)
        sleep.assert_called_once_with(1)

    @patch('bank_http.time.sleep')
    @patch('bank_http.requests.get')
    def test_timeout_retry_is_bounded_and_falls_back(self, get, sleep):
        get.side_effect = [requests.Timeout(), requests.Timeout(), response('rates')]
        self.assertTrue(bank_http.get_bank_response('https://bank.example/rates', {}, LOGGER, 'bank')[1])
        self.assertEqual(get.call_count, 3)

    @patch('bank_http.time.sleep')
    @patch('bank_http.requests.get')
    def test_permanent_block_is_not_accepted(self, get, sleep):
        get.return_value = response('Access denied', 403)
        with self.assertRaises(requests.HTTPError):
            bank_http.get_bank_response('https://bank.example/rates', {}, LOGGER, 'bank')
        self.assertEqual(get.call_count, 3)

    @patch('bank_http.requests.get')
    def test_http_200_block_page_uses_fallback(self, get):
        get.side_effect = [response('Request blocked'), response('rates')]
        self.assertTrue(bank_http.get_bank_response('https://bank.example/rates', {}, LOGGER, 'bank')[1])


class SourceTests(unittest.TestCase):
    def test_exchange_table_ignores_deposits_and_selects_currency_notes(self):
        html = ('<table><tr><td>AUD</td><td>3.25%</td><td>3.75%</td></tr></table>'
                + table('<tr><td>AUD</td><td>220.00</td><td>232.50</td>'
                        '<td>215.00</td><td>232.50</td><td>221.00</td><td>233.00</td></tr>'))
        self.assertEqual(bank_sources.parse_exchange_table(html, 'AUD'), (220.0, 232.5))

    def test_missing_and_invalid_quotes_are_rejected(self):
        for buy, sell in [('0', '337'), ('nan', '337'), ('338', '337'), ('-', '337')]:
            with self.subTest(buy=buy), self.assertRaises(ValueError):
                bank_sources.parse_exchange_table(table(f'<tr><td>USD</td><td>{buy}</td><td>{sell}</td></tr>'), 'USD')

    @patch('bank_sources.get_bank_response')
    def test_boc_empty_published_table_is_reported_as_source_outage(self, get):
        get.return_value = (response('<div id="exchange-rates">' + table('') + '</div>'), False)
        with self.assertLogs(LOGGER, level='WARNING') as captured:
            self.assertIsNone(bank_sources.scrape_boc_rates('USD', {}, LOGGER))
        self.assertIn('publishing an empty exchange-rate table', captured.output[0])

    @patch('bank_sources.get_bank_response')
    def test_all_currency_wrappers_use_shared_boc_parser(self, get):
        get.return_value = (response('<div id="exchange-rates">' + table(''.join(
            f'<tr><td>{currency}</td><td>220.00</td><td>230.00</td></tr>'
            for currency in CURRENCIES)) + '</div>'), True)
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                module = importlib.import_module(f'daily_{currency.lower()}_rate_scraper')
                quote = module.scrape_boc_rates(LOGGER)
                self.assertEqual(quote['currency'], currency)
                self.assertEqual(quote['buying_rate'], 220)
                self.assertEqual(quote['source'], 'BOC via Google Translate')

    @patch('bank_sources.get_bank_response')
    def test_combank_api_keeps_currency_note_fields(self, get):
        get.return_value = (response(json.dumps([{
            'excode': currency, 'currency_buying_rate': 220, 'currency_selling_rate': 230,
            'telegraphic_transfers_buying_rate': 225,
        } for currency in CURRENCIES]), content_type='application/json'), False)
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                module = importlib.import_module(f'daily_{currency.lower()}_rate_scraper')
                quote = module.scrape_combank_rates(LOGGER)
                self.assertEqual(quote['currency'], currency)
                self.assertEqual(quote['buying_rate'], 220)

    @patch('bank_sources.get_bank_response')
    def test_combank_api_outage_or_invalid_payload_uses_table(self, get):
        html = table(''.join(f'<tr><td>{name}</td><td>1,220.00</td><td>1,230.50</td></tr>'
                             for name in bank_sources._COMBANK_NAMES.values()))
        for currency in CURRENCIES:
            for error in (requests.HTTPError('400'), response('<html>Not JSON</html>'), response('[]')):
                with self.subTest(currency=currency, error=type(error).__name__):
                    get.side_effect = [error if isinstance(error, Exception) else (error, False),
                                       (response(html), True)]
                    quote = bank_sources.scrape_combank_rates(currency, {}, LOGGER)
                    self.assertEqual(quote['currency'], currency)
                    self.assertEqual(quote['buying_rate'], 1220)
                    self.assertEqual(quote['selling_rate'], 1230.5)
                    self.assertEqual(quote['source'], 'Combank table via Google Translate')

    @patch('bank_sources.get_bank_response')
    def test_cbsl_all_currency_wrappers_use_block_fallback(self, get):
        get.return_value = (response('<p>Indicative 332.50</p><p>Buy&nbsp; <b>328.0576</b></p>'
                                    '<p>Sell&nbsp; 337.0529</p>'), True)
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                module = importlib.import_module(f'daily_{currency.lower()}_rate_scraper')
                quote = module.scrape_cbsl_rates(LOGGER)
                self.assertEqual((quote['buying_rate'], quote['selling_rate']), (328.0576, 337.0529))
                self.assertEqual(quote['source'], 'CBSL via Google Translate')
                self.assertIn(f'/{currency.lower()}/', quote['source_url'])

    def test_summaries_report_partial_coverage_and_correct_filename(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency), tempfile.TemporaryDirectory() as directory:
                module = importlib.import_module(f'daily_{currency.lower()}_rate_scraper')
                quote = {'bank': 'Commercial Bank', 'buying_rate': 220, 'selling_rate': 230}
                with patch.object(module, 'Path', side_effect=lambda filename: Path(directory) / filename):
                    summary = module.create_execution_summary([quote], LOGGER)
                self.assertEqual(summary['coverage_status'], 'partial')
                self.assertIn('Bank of Ceylon', summary['failed_banks'])
                self.assertNotIn('Commercial Bank', summary['failed_banks'])
                self.assertTrue((Path(directory) / f'{currency.lower()}_execution_summary.json').exists())
                self.assertEqual(summary['best_rate_to_sell']['rate'], 220)


if __name__ == '__main__':
    unittest.main()
