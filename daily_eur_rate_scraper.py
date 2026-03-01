
#!/usr/bin/env python3
"""
GitHub Workflow-Friendly EUR Exchange Rate Scraper
Scrapes EUR exchange rates directly from each bank's website
Optimized for automated execution in GitHub Actions with enhanced logging and error handling
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import io
from datetime import datetime
import time
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
import json

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
except ImportError:
    pass

# PyPDF2 for HSBC
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# Load environment variables
load_dotenv()

CURRENCY = 'EUR'
CURRENCY_NAMES = ['EUR', 'Euro', 'EURO']

# Common headers for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# ============================================================
# LOGGING & ENVIRONMENT
# ============================================================

def setup_logging():
    """Setup comprehensive logging for GitHub Actions environment"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"eur_exchange_scraper_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    logger = logging.getLogger(__name__)
    logger.info(f"🚀 EUR Exchange Rate Scraper Started - Log file: {log_file}")
    logger.info(f"⏰ Execution time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"🌍 Timezone: {os.getenv('TZ', 'UTC')}")
    return logger


def log_environment_info(logger):
    """Log environment information for debugging"""
    logger.info("🔧 Environment Information:")
    logger.info(f"  Python version: {sys.version}")
    logger.info(f"  Working directory: {os.getcwd()}")
    logger.info(f"  GitHub Actions: {'Yes' if os.getenv('GITHUB_ACTIONS') else 'No'}")
    logger.info(f"  Runner OS: {os.getenv('RUNNER_OS', 'Unknown')}")
    logger.info(f"  MongoDB connection configured: {bool(os.getenv('MONGODB_CONNECTION_STRING'))}")


def create_screenshots_dir():
    """Create screenshots directory for debugging failures"""
    screenshots_dir = Path("screenshots")
    screenshots_dir.mkdir(exist_ok=True)
    return screenshots_dir


def normalize_bank_name(bank_name):
    """Normalize bank names to consistent, clean format"""
    name_lower = bank_name.lower().strip()
    bank_mappings = {
        'central bank of sri lanka': 'Central Bank of Sri Lanka',
        'amana bank': 'Amana Bank',
        'bank of ceylon': 'Bank of Ceylon',
        'boc': 'Bank of Ceylon',
        'commercial bank': 'Commercial Bank',
        'hatton national bank': 'Hatton National Bank',
        'hnb': 'Hatton National Bank',
        'hsbc bank': 'HSBC Bank',
        'hsbc': 'HSBC Bank',
        'nations trust bank': 'Nations Trust Bank',
        'ntb': 'Nations Trust Bank',
        "people's bank": "People's Bank",
        'peoples bank': "People's Bank",
        'sampath bank': 'Sampath Bank'
    }
    if name_lower in bank_mappings:
        return bank_mappings[name_lower]
    for key, value in bank_mappings.items():
        if key in name_lower or name_lower in key:
            return value
    return bank_name.title()


# ============================================================
# MONGODB
# ============================================================

class ExchangeRateDB:
    """MongoDB handler optimized for GitHub Actions execution"""

    def __init__(self, connection_string=None, db_name="exchange_rates", logger=None):
        self.logger = logger or logging.getLogger(__name__)

        if connection_string is None:
            connection_string = os.getenv('MONGODB_CONNECTION_STRING')

        if not connection_string:
            error_msg = "MongoDB connection string not provided. Set MONGODB_CONNECTION_STRING secret."
            self.logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

        try:
            self.client = MongoClient(
                connection_string,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000
            )
            self.db = self.client[db_name]
            self.collection = self.db.daily_eur_rates
            self.collection.create_index([("date", ASCENDING)], unique=True)
            self.client.admin.command('ping')
            self.logger.info(f"✅ Connected to MongoDB Atlas database: {db_name}")

        except ConnectionFailure as e:
            self.logger.error(f"❌ Failed to connect to MongoDB Atlas: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ MongoDB connection error: {e}")
            raise

    def create_daily_document(self, bank_data_list):
        """Create or update daily document with bank exchange rates"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_datetime = datetime.now()

        bank_rates = {}
        bank_summary = []

        for bank_info in bank_data_list:
            bank_name = bank_info['bank']
            bank_rates[bank_name] = {
                'buying_rate': bank_info['buying_rate'],
                'selling_rate': bank_info['selling_rate'],
                'spread': bank_info['selling_rate'] - bank_info['buying_rate'],
                'last_updated': current_datetime,
                'source': bank_info.get('source', 'direct')
            }
            bank_summary.append({
                'bank_name': bank_name,
                'buying_rate': bank_info['buying_rate'],
                'selling_rate': bank_info['selling_rate'],
                'spread': bank_info['selling_rate'] - bank_info['buying_rate'],
                'source': bank_info.get('source', 'direct')
            })

        buying_rates = [bank['buying_rate'] for bank in bank_data_list]
        selling_rates = [bank['selling_rate'] for bank in bank_data_list]

        market_stats = {
            'people_selling': {
                'min': min(buying_rates),
                'max': max(buying_rates),
                'avg': sum(buying_rates) / len(buying_rates),
                'best_bank': max(bank_data_list, key=lambda x: x['buying_rate'])['bank']
            },
            'people_buying': {
                'min': min(selling_rates),
                'max': max(selling_rates),
                'avg': sum(selling_rates) / len(selling_rates),
                'best_bank': min(bank_data_list, key=lambda x: x['selling_rate'])['bank']
            }
        }

        document = {
            'date': current_date,
            'last_updated': current_datetime,
            'currency': CURRENCY,
            'source': 'direct_bank_scraping',
            'total_banks': len(bank_data_list),
            'bank_rates': bank_rates,
            'bank_summary': bank_summary,
            'market_statistics': market_stats,
            'execution_environment': {
                'github_actions': bool(os.getenv('GITHUB_ACTIONS')),
                'runner_os': os.getenv('RUNNER_OS', 'unknown'),
                'workflow_run_id': os.getenv('GITHUB_RUN_ID'),
                'timezone': os.getenv('TZ', 'UTC')
            },
            'data_completeness': {
                'banks_updated': list(bank_rates.keys()),
                'banks_count': len(bank_rates),
                'update_timestamp': current_datetime
            }
        }
        return document

    def upsert_daily_rates(self, bank_data_list):
        """Insert or update daily exchange rates with enhanced logging"""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            new_document = self.create_daily_document(bank_data_list)

            existing = self.collection.find_one({'date': current_date})

            if existing:
                existing_banks = existing.get('bank_rates', {})
                new_banks = new_document['bank_rates']
                merged_banks = {**existing_banks, **new_banks}
                merged_summary = []
                for bank_name, bank_data in merged_banks.items():
                    merged_summary.append({
                        'bank_name': bank_name,
                        'buying_rate': bank_data['buying_rate'],
                        'selling_rate': bank_data['selling_rate'],
                        'spread': bank_data['spread'],
                        'source': bank_data.get('source', 'direct')
                    })

                all_buying = [b['buying_rate'] for b in merged_summary]
                all_selling = [b['selling_rate'] for b in merged_summary]

                updated_market_stats = {
                    'people_selling': {
                        'min': min(all_buying),
                        'max': max(all_buying),
                        'avg': sum(all_buying) / len(all_buying),
                        'best_bank': max(merged_summary, key=lambda x: x['buying_rate'])['bank_name']
                    },
                    'people_buying': {
                        'min': min(all_selling),
                        'max': max(all_selling),
                        'avg': sum(all_selling) / len(all_selling),
                        'best_bank': min(merged_summary, key=lambda x: x['selling_rate'])['bank_name']
                    }
                }

                update_data = {
                    '$set': {
                        'last_updated': datetime.now(),
                        'total_banks': len(merged_banks),
                        'bank_rates': merged_banks,
                        'bank_summary': merged_summary,
                        'market_statistics': updated_market_stats,
                        'execution_environment': new_document['execution_environment'],
                        'data_completeness.banks_updated': list(new_banks.keys()),
                        'data_completeness.banks_count': len(merged_banks),
                        'data_completeness.update_timestamp': datetime.now()
                    }
                }

                self.collection.update_one({'date': current_date}, update_data)
                self.logger.info(f"✅ Updated document for {current_date}")
                self.logger.info(f"📊 Previous banks: {list(existing_banks.keys())}")
                self.logger.info(f"🔄 Updated banks: {list(new_banks.keys())}")
                self.logger.info(f"📈 Total banks now: {len(merged_banks)}")
            else:
                self.collection.insert_one(new_document)
                self.logger.info(f"🆕 Created new document for {current_date}")
                self.logger.info(f"📊 Banks added: {list(new_document['bank_rates'].keys())}")

            return True

        except Exception as e:
            self.logger.error(f"❌ Error saving to MongoDB Atlas: {e}")
            return False

    def get_daily_rates(self, date=None):
        """Get exchange rates for a specific date"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        return self.collection.find_one({'date': date})

    def close_connection(self):
        """Close MongoDB connection"""
        if hasattr(self, 'client'):
            self.client.close()
            self.logger.info("🔌 MongoDB connection closed")


# ============================================================
# SELENIUM SETUP
# ============================================================

def setup_selenium_for_github_actions():
    """Setup Selenium WebDriver optimized for GitHub Actions"""
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        if os.getenv('GITHUB_ACTIONS'):
            chrome_options.binary_location = '/usr/bin/google-chrome'

        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        return driver

    except NameError:
        logging.error("❌ Selenium is not installed")
        return None
    except Exception as e:
        logging.error(f"❌ Error setting up Chrome driver: {e}")
        return None


# ============================================================
# DIRECT BANK SCRAPING FUNCTIONS
# ============================================================

def scrape_boc_rates(logger):
    """Scrape EUR exchange rates from Bank of Ceylon website"""
    url = "https://www.boc.lk/rates-tariff"
    try:
        logger.info("🏦 Scraping Bank of Ceylon...")
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')

        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]

                # BOC uses currency code as first cell (e.g., 'EUR')
                if len(row_text) > 0 and row_text[0] == CURRENCY and len(row_text) >= 3:
                    numeric_values = []
                    for cell in row_text[1:]:
                        numbers = re.findall(r'\d+\.\d+', cell)
                        for num in numbers:
                            if float(num) > 50:
                                numeric_values.append(float(num))

                    if len(numeric_values) >= 2:
                        result = {
                            'bank': normalize_bank_name('Bank of Ceylon'),
                            'currency': CURRENCY,
                            'buying_rate': numeric_values[0],
                            'selling_rate': numeric_values[1],
                            'source': 'BOC Direct',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': url
                        }
                        logger.info(f"  ✅ BOC - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                        return result

        logger.warning(f"  ⚠️ {CURRENCY} not found in BOC tables")
        return None

    except Exception as e:
        logger.error(f"  ❌ Error scraping BOC: {e}")
        return None


def scrape_combank_rates(logger):
    """Scrape EUR exchange rates from Commercial Bank website"""
    url = "https://www.combank.lk/rates-tariff#exchange-rates"
    try:
        logger.info("🏦 Scraping Commercial Bank...")
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')

        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]

                # Combank uses 'EURO'
                if len(row_text) > 0 and any('EURO' in cell.upper() for cell in row_text):
                    numeric_values = []
                    for cell in row_text[1:]:
                        numbers = re.findall(r'\d+\.\d+', cell)
                        for num in numbers:
                            if float(num) > 50:
                                numeric_values.append(float(num))

                    if len(numeric_values) >= 2:
                        result = {
                            'bank': normalize_bank_name('Commercial Bank'),
                            'currency': CURRENCY,
                            'buying_rate': numeric_values[0],
                            'selling_rate': numeric_values[1],
                            'source': 'Combank Direct',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': url
                        }
                        logger.info(f"  ✅ Combank - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                        return result

        logger.warning(f"  ⚠️ {CURRENCY} not found in Combank tables")
        return None

    except Exception as e:
        logger.error(f"  ❌ Error scraping Combank: {e}")
        return None


def scrape_amana_rates(logger):
    """Scrape EUR exchange rates from Amana Bank website"""
    url = "https://www.amanabank.lk/business/treasury/exchange-rates.html"
    try:
        logger.info("🏦 Scraping Amana Bank...")
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')

        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]

                # Match currency using CURRENCY_NAMES list
                if len(row_text) > 0 and any(name in c for c in row_text for name in CURRENCY_NAMES):
                    numeric_values = []
                    for cell in row_text[1:]:
                        numbers = re.findall(r'\d+\.\d+', cell)
                        for num in numbers:
                            if float(num) > 50:
                                numeric_values.append(float(num))

                    if len(numeric_values) >= 2:
                        result = {
                            'bank': normalize_bank_name('Amana Bank'),
                            'currency': CURRENCY,
                            'buying_rate': numeric_values[0],
                            'selling_rate': numeric_values[1],
                            'source': 'Amana Direct',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': url
                        }
                        logger.info(f"  ✅ Amana - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                        return result

        logger.warning(f"  ⚠️ {CURRENCY} not found in Amana tables")
        return None

    except Exception as e:
        logger.error(f"  ❌ Error scraping Amana Bank: {e}")
        return None


def scrape_peoples_bank_rates(logger):
    """Scrape EUR exchange rates from People's Bank website"""
    url = "https://www.peoplesbank.lk/exchange-rates/"
    try:
        logger.info("🏦 Scraping People's Bank...")
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')

        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]

                if len(row_text) > 0 and any('Euro' in cell for cell in row_text):
                    numeric_values = []
                    for cell in row_text[1:]:
                        clean_cell = cell.replace(',', '')
                        numbers = re.findall(r'\d+\.\d+', clean_cell)
                        for num in numbers:
                            if float(num) > 50:
                                numeric_values.append(float(num))

                    if len(numeric_values) >= 2:
                        result = {
                            'bank': normalize_bank_name("People's Bank"),
                            'currency': CURRENCY,
                            'buying_rate': numeric_values[0],
                            'selling_rate': numeric_values[1],
                            'source': "People's Bank Direct",
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': url
                        }
                        logger.info(f"  ✅ People's Bank - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                        return result

        logger.warning(f"  ⚠️ {CURRENCY} not found in People's Bank tables")
        return None

    except Exception as e:
        logger.error(f"  ❌ Error scraping People's Bank: {e}")
        return None


def scrape_hsbc_rates(logger):
    """Scrape EUR exchange rates from HSBC PDF"""
    url = "https://www.hsbc.lk/content/dam/hsbc/lk/documents/tariffs/foreign-exchange-rates.pdf"
    try:
        logger.info("🏦 Scraping HSBC (PDF)...")

        if PyPDF2 is None:
            logger.error("  ❌ PyPDF2 not installed. Install with: pip install PyPDF2")
            return None

        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        reader = PyPDF2.PdfReader(io.BytesIO(response.content))

        for page in reader.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split('\n'):
                # Look for the EUR line
                if CURRENCY in line and any(name in line for name in ['Euro', 'EUR']):
                    numbers = re.findall(r'\d+\.\d+', line)
                    exchange_rates = [float(num) for num in numbers if float(num) > 50]

                    if len(exchange_rates) >= 2:
                        result = {
                            'bank': normalize_bank_name('HSBC Bank'),
                            'currency': CURRENCY,
                            'buying_rate': exchange_rates[0],
                            'selling_rate': exchange_rates[1],
                            'source': 'HSBC PDF',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': url
                        }
                        logger.info(f"  ✅ HSBC - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                        return result

        logger.warning(f"  ⚠️ {CURRENCY} not found in HSBC PDF")
        return None

    except Exception as e:
        logger.error(f"  ❌ Error scraping HSBC PDF: {e}")
        return None


def scrape_hnb_rates(logger, screenshots_dir):
    """Scrape EUR exchange rates from HNB website using Selenium"""
    url = "https://www.hnb.lk/"
    driver = None
    try:
        logger.info("🏦 Scraping HNB (Selenium)...")
        driver = setup_selenium_for_github_actions()
        if not driver:
            return None

        driver.get(url)
        wait = WebDriverWait(driver, 20)

        # Strategy 1: Look for exchange rate elements on HNB page
        try:
            wait.until(
                EC.presence_of_all_elements_located((By.XPATH, "//*[contains(text(), 'USD') or contains(text(), 'Exchange') or contains(text(), 'Rate')]"))
            )
            time.sleep(5)

            aud_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'EUR')]")
            for element in aud_elements:
                parent = element
                for _ in range(5):
                    try:
                        parent_text = parent.text
                        numbers = re.findall(r'(\d{2,3}\.\d{1,4})', parent_text)
                        valid_rates = [float(num) for num in numbers if 100 <= float(num) <= 500]

                        if len(valid_rates) >= 2:
                            valid_rates.sort()
                            result = {
                                'bank': normalize_bank_name('Hatton National Bank'),
                                'currency': CURRENCY,
                                'buying_rate': valid_rates[0],
                                'selling_rate': valid_rates[1],
                                'source': 'HNB Direct',
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'source_url': url
                            }
                            logger.info(f"  ✅ HNB - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                            return result
                        parent = parent.find_element(By.XPATH, "..")
                    except:
                        break
        except TimeoutException:
            pass

        # Strategy 2: Search page source
        try:
            page_source = driver.page_source
            aud_pattern = r'(?i)(?:EUR|Euro).*?(\d{2,3}\.\d{1,4}).*?(\d{2,3}\.\d{1,4})'
            matches = re.findall(aud_pattern, page_source)

            for match in matches:
                rates = [float(rate) for rate in match if 100 <= float(rate) <= 500]
                if len(rates) >= 2:
                    rates.sort()
                    result = {
                        'bank': normalize_bank_name('Hatton National Bank'),
                        'currency': CURRENCY,
                        'buying_rate': rates[0],
                        'selling_rate': rates[1],
                        'source': 'HNB Direct',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'source_url': url
                    }
                    logger.info(f"  ✅ HNB - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                    return result
        except Exception:
            pass

        logger.warning("  ⚠️ HNB scraping failed")
        return None

    except Exception as e:
        logger.error(f"  ❌ Error scraping HNB: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def scrape_ntb_rates(logger, screenshots_dir):
    """Scrape EUR exchange rates from NTB website using text parsing"""
    url = "https://www.nationstrust.com/foreign-exchange-rates"
    try:
        logger.info("🏦 Scraping NTB...")
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        page_text = soup.get_text()

        if CURRENCY not in page_text:
            logger.warning(f"  ⚠️ {CURRENCY} not found in NTB page")
            return None

        # NTB page structure: currency code on one line, then rates on subsequent lines
        # Pattern: CURRENCY_CODE / DD_Buy / DD_Sell / TT_Buy / TT_Sell / ...
        lines = [l.strip() for l in page_text.split('\n') if l.strip()]

        for i, line in enumerate(lines):
            if line == CURRENCY:
                # Collect numeric values from the following lines
                numeric_values = []
                for j in range(i + 1, min(i + 10, len(lines))):
                    try:
                        val = float(lines[j].replace(',', ''))
                        if val > 50:
                            numeric_values.append(val)
                    except ValueError:
                        break  # Stop at non-numeric line

                if len(numeric_values) >= 2:
                    # First two values are DD Buying and DD Selling
                    # Use TT rates if available (positions 2,3), else DD (0,1)
                    buy_idx, sell_idx = (2, 3) if len(numeric_values) >= 4 else (0, 1)
                    result = {
                        'bank': normalize_bank_name('Nations Trust Bank'),
                        'currency': CURRENCY,
                        'buying_rate': numeric_values[buy_idx],
                        'selling_rate': numeric_values[sell_idx],
                        'source': 'NTB Direct',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'source_url': url
                    }
                    logger.info(f"  ✅ NTB - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                    return result

        logger.warning(f"  ⚠️ {CURRENCY} rates not found in NTB text")
        return None

    except Exception as e:
        logger.error(f"  ❌ Error scraping NTB: {e}")
        return None


def scrape_sampath_rates(logger, screenshots_dir):
    """Scrape EUR exchange rates from Sampath Bank JSON API"""
    api_url = "https://www.sampath.lk/api/exchange-rates"
    try:
        logger.info("🏦 Scraping Sampath Bank (API)...")
        response = requests.get(api_url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        data = response.json()

        if not data.get('success') or not data.get('data'):
            logger.warning("  ⚠️ Sampath API returned no data")
            return None

        for rate_entry in data['data']:
            if rate_entry.get('CurrCode') == CURRENCY:
                tt_buy = float(rate_entry['TTBUY'])
                tt_sell = float(rate_entry['TTSEL'])

                result = {
                    'bank': normalize_bank_name('Sampath Bank'),
                    'currency': CURRENCY,
                    'buying_rate': tt_buy,
                    'selling_rate': tt_sell,
                    'source': 'Sampath API',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'source_url': api_url
                }
                logger.info(f"  ✅ Sampath - Buy: {result['buying_rate']}, Sell: {result['selling_rate']}")
                return result

        logger.warning(f"  ⚠️ {CURRENCY} not found in Sampath API data")
        return None

    except Exception as e:
        logger.error(f"  ❌ Error scraping Sampath API: {e}")
        return None



# ============================================================
# OUTPUT & SUMMARY
# ============================================================

def create_execution_summary(bank_data_list, logger):
    """Create execution summary for GitHub Actions"""
    summary_data = {
        'execution_time': datetime.now().isoformat(),
        'currency': CURRENCY,
        'total_banks_scraped': len(bank_data_list),
        'banks_list': [bank['bank'] for bank in bank_data_list],
        'sources_used': list(set(bank.get('source', 'direct') for bank in bank_data_list)),
        'github_actions': bool(os.getenv('GITHUB_ACTIONS')),
        'workflow_run_id': os.getenv('GITHUB_RUN_ID'),
        'runner_os': os.getenv('RUNNER_OS', 'unknown'),
        'timezone': os.getenv('TZ', 'UTC'),
        'execution_status': 'success' if bank_data_list else 'failed'
    }

    if bank_data_list:
        best_selling_bank = max(bank_data_list, key=lambda x: x['buying_rate'])
        best_buying_bank = min(bank_data_list, key=lambda x: x['selling_rate'])

        summary_data.update({
            'best_rate_to_sell': {
                'bank': best_selling_bank['bank'],
                'rate': best_selling_bank['buying_rate']
            },
            'best_rate_to_buy': {
                'bank': best_buying_bank['bank'],
                'rate': best_buying_bank['selling_rate']
            },
            'average_buying_rate': sum(bank['buying_rate'] for bank in bank_data_list) / len(bank_data_list),
            'average_selling_rate': sum(bank['selling_rate'] for bank in bank_data_list) / len(bank_data_list)
        })

    summary_file = Path(f"{CURRENCY.lower()}_execution_summary.json")
    with open(summary_file, 'w') as f:
        json.dump(summary_data, f, indent=2, default=str)

    logger.info(f"📋 Execution summary saved to {summary_file}")
    return summary_data


def print_bank_rates(bank_data_list, logger):
    """Print bank rates in a formatted way"""
    if not bank_data_list:
        logger.error("❌ No bank data found")
        return

    logger.info("=" * 80)
    logger.info(f"🏦 ALL BANKS - {CURRENCY} EXCHANGE RATES (People's Perspective)")
    logger.info("=" * 80)

    for bank_info in bank_data_list:
        spread = bank_info['selling_rate'] - bank_info['buying_rate']
        logger.info(f"🏦 {bank_info['bank']} [{bank_info.get('source', 'N/A')}]")
        logger.info(f"   💰 Sell {CURRENCY} For: LKR {bank_info['buying_rate']:.2f}")
        logger.info(f"   💸 Buy {CURRENCY} For:  LKR {bank_info['selling_rate']:.2f}")
        logger.info(f"   📊 Spread:       LKR {spread:.4f}")
        logger.info("-" * 50)

    best_selling_bank = max(bank_data_list, key=lambda x: x['buying_rate'])
    best_buying_bank = min(bank_data_list, key=lambda x: x['selling_rate'])

    logger.info(f"🎯 BEST {CURRENCY} RATES FOR YOU:")
    logger.info(f"✅ Best to Sell {CURRENCY}: LKR {best_selling_bank['buying_rate']:.2f} at {best_selling_bank['bank']}")
    logger.info(f"✅ Best to Buy {CURRENCY}:  LKR {best_buying_bank['selling_rate']:.2f} at {best_buying_bank['bank']}")
    logger.info(f"📈 Total Banks: {len(bank_data_list)}")

    sources = {}
    for bank in bank_data_list:
        source = bank.get('source', 'direct')
        sources[source] = sources.get(source, 0) + 1
    logger.info(f"📡 Data Sources: {dict(sources)}")
    logger.info("=" * 80)


# ============================================================
# MAIN
# ============================================================

def main():
    """Main execution function - scrapes all banks directly"""
    logger = setup_logging()
    log_environment_info(logger)
    screenshots_dir = create_screenshots_dir()

    db = None
    exit_code = 0

    try:
        logger.info(f"🔗 Connecting to MongoDB Atlas for {CURRENCY} data...")
        db = ExchangeRateDB(logger=logger)

        all_bank_data = []
        failed_banks = []

        # Step 1: BOC (requests + BS4)
        # Step 1: BOC (requests + BS4)
        logger.info(f"📡 Step 1/8: Bank of Ceylon")
        result = scrape_boc_rates(logger)
        if result and result.get('buying_rate'):
            all_bank_data.append(result)
        else:
            failed_banks.append('BOC')

        # Step 2: Commercial Bank (requests + BS4)
        logger.info(f"📡 Step 2/8: Commercial Bank")
        result = scrape_combank_rates(logger)
        if result and result.get('buying_rate'):
            all_bank_data.append(result)
        else:
            failed_banks.append('Commercial Bank')

        # Step 3: Amana Bank (requests + BS4)
        logger.info(f"📡 Step 3/8: Amana Bank")
        result = scrape_amana_rates(logger)
        if result and result.get('buying_rate'):
            all_bank_data.append(result)
        else:
            failed_banks.append('Amana Bank')

        # Step 4: People's Bank (requests + BS4)
        logger.info(f"📡 Step 4/8: People's Bank")
        result = scrape_peoples_bank_rates(logger)
        if result and result.get('buying_rate'):
            all_bank_data.append(result)
        else:
            failed_banks.append("People's Bank")

        # Step 5: HSBC (PyPDF2)
        logger.info(f"📡 Step 5/8: HSBC")
        result = scrape_hsbc_rates(logger)
        if result and result.get('buying_rate'):
            all_bank_data.append(result)
        else:
            failed_banks.append('HSBC')

        # Step 6: HNB (Selenium)
        logger.info(f"📡 Step 6/8: Hatton National Bank")
        result = scrape_hnb_rates(logger, screenshots_dir)
        if result and result.get('buying_rate'):
            all_bank_data.append(result)
        else:
            failed_banks.append('HNB')

        # Step 7: NTB (text parsing)
        logger.info(f"📡 Step 7/8: Nations Trust Bank")
        result = scrape_ntb_rates(logger, screenshots_dir)
        if result and result.get('buying_rate'):
            all_bank_data.append(result)
        else:
            failed_banks.append('NTB')

        # Step 8: Sampath Bank (JSON API)
        logger.info(f"📡 Step 8/8: Sampath Bank")
        result = scrape_sampath_rates(logger, screenshots_dir)
        if result and result.get('buying_rate'):
            all_bank_data.append(result)
        else:
            failed_banks.append('Sampath Bank')

        # Summary
        logger.info(f"\n📊 Scraping complete: {len(all_bank_data)}/8 banks successful")
        if failed_banks:
            logger.warning(f"⚠️ Failed banks: {', '.join(failed_banks)}")

        # Display and save results
        if all_bank_data:
            print_bank_rates(all_bank_data, logger)

            success = db.upsert_daily_rates(all_bank_data)

            if success:
                logger.info(f"🎉 [SUCCESS] Saved {len(all_bank_data)} {CURRENCY} banks to MongoDB Atlas")
                bank_names = [bank['bank'] for bank in all_bank_data]
                logger.info(f"🏦 {CURRENCY} Banks: {', '.join(bank_names)}")

                today_data = db.get_daily_rates()
                if today_data:
                    logger.info(f"📊 Today's {CURRENCY} document contains {today_data['total_banks']} banks")
                    stats = today_data['market_statistics']
                    logger.info(f"🟢 Best {CURRENCY} Sell Rate: {stats['people_selling']['best_bank']} (LKR {stats['people_selling']['max']})")
                    logger.info(f"🔵 Best {CURRENCY} Buy Rate: {stats['people_buying']['best_bank']} (LKR {stats['people_buying']['min']})")

                create_execution_summary(all_bank_data, logger)
                logger.info(f"✨ {CURRENCY} Execution completed successfully!")
            else:
                logger.error(f"❌ [ERROR] Failed to save {CURRENCY} data to MongoDB Atlas")
                exit_code = 1
        else:
            logger.error(f"❌ [ERROR] Failed to scrape any {CURRENCY} bank data")
            exit_code = 1

    except Exception as e:
        logger.error(f"❌ Critical {CURRENCY} scraping error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        exit_code = 1

    finally:
        if db:
            db.close_connection()

        if exit_code == 0:
            logger.info(f"🏁 {CURRENCY} Script execution completed successfully")
        else:
            logger.error(f"🏁 {CURRENCY} Script execution failed")

        sys.exit(exit_code)


if __name__ == "__main__":
    main()