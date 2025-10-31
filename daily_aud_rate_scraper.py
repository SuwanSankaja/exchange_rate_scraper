
#!/usr/bin/env python3
"""
GitHub Workflow-Friendly AUD Exchange Rate Scraper
Optimized for automated execution in GitHub Actions with enhanced logging and error handling
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
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

# Selenium imports are now centralized
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
except ImportError:
    # This will be handled gracefully in functions that require Selenium
    pass

# Load environment variables
load_dotenv()

# Configure logging for GitHub Actions
def setup_logging():
    """Setup comprehensive logging for GitHub Actions environment"""

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Create timestamped log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"exchange_scraper_{timestamp}.log"

    # Configure logging with explicit encoding for handlers
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout) # For GitHub Actions console
        ]
    )
    
    # For Windows console, it's often best to set the environment variable
    # PYTHONIOENCODING=utf-8 before running the script.
    # However, we can also try to reconfigure stdout for the current run.
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception as e:
            # In some environments this is not possible, but we try.
            # The FileHandler will still work correctly.
            logging.getLogger(__name__).warning(f"Could not reconfigure stdout to utf-8: {e}")


    logger = logging.getLogger(__name__)
    logger.info(f"🚀 Exchange Rate Scraper Started - Log file: {log_file}")
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

    # Check if MongoDB connection string is available (without exposing it)
    mongo_available = bool(os.getenv('MONGODB_CONNECTION_STRING'))
    logger.info(f"  MongoDB connection configured: {mongo_available}")

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
                serverSelectionTimeoutMS=10000,  # 10 seconds timeout
                connectTimeoutMS=10000,
                socketTimeoutMS=10000
            )
            self.db = self.client[db_name]
            self.collection = self.db.daily_aud_rates

            # Create index on date for faster queries
            self.collection.create_index([("date", ASCENDING)], unique=True)

            # Test connection
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

        # Create the bank rates dictionary
        bank_rates = {}
        bank_summary = []

        for bank_info in bank_data_list:
            bank_name = bank_info['bank']

            # Individual bank data
            bank_rates[bank_name] = {
                'buying_rate': bank_info['buying_rate'],
                'selling_rate': bank_info['selling_rate'],
                'spread': bank_info['selling_rate'] - bank_info['buying_rate'],
                'last_updated': current_datetime,
                'source': bank_info.get('source', 'numbers.lk')
            }

            # Summary data for easy visualization
            bank_summary.append({
                'bank_name': bank_name,
                'buying_rate': bank_info['buying_rate'],
                'selling_rate': bank_info['selling_rate'],
                'spread': bank_info['selling_rate'] - bank_info['buying_rate'],
                'source': bank_info.get('source', 'numbers.lk')
            })

        # Calculate market statistics (people's perspective)
        buying_rates = [bank['buying_rate'] for bank in bank_data_list]
        selling_rates = [bank['selling_rate'] for bank in bank_data_list]

        market_stats = {
            'people_selling': {  # People selling AUD (bank buying)
                'min': min(buying_rates),  # Worst rate for people
                'max': max(buying_rates),  # Best rate for people
                'avg': sum(buying_rates) / len(buying_rates),
                'best_bank': max(bank_data_list, key=lambda x: x['buying_rate'])['bank']
            },
            'people_buying': {  # People buying AUD (bank selling)
                'min': min(selling_rates),  # Best rate for people
                'max': max(selling_rates),  # Worst rate for people
                'avg': sum(selling_rates) / len(selling_rates),
                'best_bank': min(bank_data_list, key=lambda x: x['selling_rate'])['bank']
            }
        }

        # Document structure optimized for visualization
        document = {
            'date': current_date,
            'last_updated': current_datetime,
            'currency': 'AUD',
            'source': 'numbers.lk + direct_scraping',
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
        if not bank_data_list:
            self.logger.warning("⚠️ No bank data to save")
            return False

        current_date = datetime.now().strftime('%Y-%m-%d')
        new_document = self.create_daily_document(bank_data_list)

        try:
            # Check if document for today already exists
            existing_doc = self.collection.find_one({'date': current_date})

            if existing_doc:
                self.logger.info(f"📝 Found existing document for {current_date}. Updating...")

                # Preserve existing bank data and update only new banks
                existing_banks = existing_doc.get('bank_rates', {})
                new_banks = new_document['bank_rates']

                # Merge bank data
                merged_banks = existing_banks.copy()
                merged_banks.update(new_banks)

                # Update bank summary
                merged_summary = []
                for bank_name, bank_data in merged_banks.items():
                    merged_summary.append({
                        'bank_name': bank_name,
                        'buying_rate': bank_data['buying_rate'],
                        'selling_rate': bank_data['selling_rate'],
                        'spread': bank_data['spread'],
                        'source': bank_data.get('source', 'numbers.lk')
                    })

                # Recalculate market statistics
                all_buying = [bank['buying_rate'] for bank in merged_summary]
                all_selling = [bank['selling_rate'] for bank in merged_summary]

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

                # Update the document
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

                result = self.collection.update_one({'date': current_date}, update_data)
                self.logger.info(f"✅ Updated document for {current_date}")
                self.logger.info(f"📊 Previous banks: {list(existing_banks.keys())}")
                self.logger.info(f"🔄 Updated banks: {list(new_banks.keys())}")
                self.logger.info(f"📈 Total banks now: {len(merged_banks)}")

            else:
                # Insert new document
                result = self.collection.insert_one(new_document)
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

def setup_selenium_for_github_actions():
    """Setup Selenium WebDriver optimized for GitHub Actions with automatic ChromeDriver management"""
    try:
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Chrome options optimized for GitHub Actions and general scraping
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
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Use system Chrome in GitHub Actions
        if os.getenv('GITHUB_ACTIONS'):
            chrome_options.binary_location = '/usr/bin/google-chrome'

        # Use webdriver-manager to automatically download and manage ChromeDriver
        logging.info("🔧 Using webdriver-manager to install matching ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        
        logging.info("✅ ChromeDriver successfully initialized")
        return driver

    except ImportError as e:
        logging.error(f"❌ Missing required package: {e}")
        logging.error("   Please install: pip install selenium webdriver-manager")
        return None
    except Exception as e:
        logging.error(f"❌ Error setting up Chrome driver: {e}")
        return None

def scrape_ntb_aud_rates(logger):
    """
    Scrape AUD exchange rates directly from NTB with enhanced error handling
    """
    url = "https://www.nationstrust.com/foreign-exchange-rates"

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    try:
        logger.info("🌐 Scraping NTB directly from their website...")

        # Send GET request with timeout
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')

        aud_data = {
            'bank': 'Nations Trust Bank',
            'currency': 'AUD',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'NTB Direct',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }

        # Check if AUD data exists
        page_text = soup.get_text()
        if 'AUD' not in page_text:
            logger.warning("❌ AUD not found in NTB page content")
            return None

        # Try to find AUD in tables
        tables = soup.find_all('table')
        logger.info(f"🔍 Found {len(tables)} tables on NTB page")

        for table_idx, table in enumerate(tables):
            rows = table.find_all('tr')

            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]

                # Look for AUD in the row
                if any('AUD' in cell for cell in row_text):
                    logger.info(f"✅ Found AUD in NTB table {table_idx + 1}, row {row_idx + 1}")

                    # Extract numeric values
                    numeric_values = []
                    for cell in row_text:
                        clean_cell = cell.replace(',', '').replace(' ', '')
                        numbers = re.findall(r'\d+\.\d+', clean_cell)
                        for num in numbers:
                            if float(num) > 50:
                                numeric_values.append(float(num))

                    logger.info(f"📊 NTB numeric values found: {numeric_values}")

                    if len(numeric_values) >= 2:
                        aud_data['buying_rate'] = numeric_values[0]
                        aud_data['selling_rate'] = numeric_values[1]
                        logger.info(f"✅ NTB Direct - Buy: {numeric_values[0]}, Sell: {numeric_values[1]}")
                        return aud_data

        logger.warning("❌ No AUD rates found in NTB tables")
        return None

    except requests.RequestException as e:
        logger.error(f"❌ Error fetching NTB webpage: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error parsing NTB data: {e}")
        return None

def scrape_ntb_with_selenium(logger, screenshots_dir):
    """
    Selenium-based NTB scraping with screenshot capture for debugging
    """
    driver = None
    try:
        logger.info("🚀 Trying NTB with Selenium WebDriver...")

        driver = setup_selenium_for_github_actions()
        if not driver:
            return None

        try:
            logger.info("🌐 Loading NTB page with Selenium...")
            driver.get("https://www.nationstrust.com/foreign-exchange-rates")

            # Take screenshot for debugging
            screenshot_path = screenshots_dir / f"ntb_page_{datetime.now().strftime('%H%M%S')}.png"
            driver.save_screenshot(str(screenshot_path))
            logger.info(f"📸 Screenshot saved: {screenshot_path}")

            # Wait for page to load
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )

            time.sleep(3)  # Additional wait for dynamic content

            # Check for AUD
            page_source = driver.page_source
            if 'AUD' not in page_source:
                logger.warning("❌ AUD not found in Selenium page source")
                return None

            # Find AUD data
            rows = driver.find_elements(By.TAG_NAME, "tr")
            logger.info(f"🔍 Selenium found {len(rows)} total rows")

            for row_idx, row in enumerate(rows):
                row_text = row.text.strip()
                if 'AUD' in row_text:
                    logger.info(f"✅ Found AUD row {row_idx + 1}: {row_text[:100]}...")

                    # Extract rates
                    numbers = re.findall(r'\d+\.\d+', row_text.replace(',', ''))
                    exchange_rates = [float(num) for num in numbers if float(num) > 50]

                    logger.info(f"📊 NTB Selenium rates: {exchange_rates}")

                    if len(exchange_rates) >= 2:
                        return {
                            'bank': 'Nations Trust Bank',
                            'currency': 'AUD',
                            'buying_rate': exchange_rates[0],
                            'selling_rate': exchange_rates[1],
                            'source': 'NTB Selenium',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': "https://www.nationstrust.com/foreign-exchange-rates"
                        }

            logger.warning("❌ No AUD rates found with Selenium")
            return None

        finally:
            if driver:
                driver.quit()

    except (NameError, ImportError):
        logger.error("❌ Selenium not installed")
        return None
    except Exception as e:
        logger.error(f"❌ Selenium scraping error for NTB: {e}")
        return None

def scrape_numbers_lk_aud_rates(logger, screenshots_dir):
    """Scrape all AUD exchange rates from numbers.lk with enhanced logging"""
    url = "https://tools.numbers.lk/exrates"
    driver = None
    try:
        logger.info("🚀 Setting up Selenium driver for numbers.lk...")
        driver = setup_selenium_for_github_actions()
        if not driver:
            return []

        try:
            logger.info("🌐 Loading numbers.lk exchange rates page...")
            driver.get(url)

            # Take screenshot for debugging
            screenshot_path = screenshots_dir / f"numbers_lk_initial_{datetime.now().strftime('%H%M%S')}.png"
            driver.save_screenshot(str(screenshot_path))
            logger.info(f"📸 Initial screenshot saved: {screenshot_path}")

            time.sleep(3)

            logger.info("🔍 Looking for AUD currency option...")

            # Try different selectors to find AUD
            aud_selectors = [
                "//div[contains(text(), 'AUD')]",
                "//span[contains(text(), 'AUD')]",
                "//button[contains(text(), 'AUD')]",
                "//a[contains(text(), 'AUD')]",
                "//*[contains(text(), 'AUD')]"
            ]

            aud_element = None
            for selector in aud_selectors:
                try:
                    aud_element = driver.find_element(By.XPATH, selector)
                    logger.info(f"✅ Found AUD element with selector: {selector}")
                    break
                except:
                    continue

            if aud_element:
                driver.execute_script("arguments[0].click();", aud_element)
                logger.info("🖱️ Clicked on AUD currency")
                time.sleep(5)

                # Take screenshot after clicking
                screenshot_path = screenshots_dir / f"numbers_lk_after_click_{datetime.now().strftime('%H%M%S')}.png"
                driver.save_screenshot(str(screenshot_path))
                logger.info(f"📸 Post-click screenshot saved: {screenshot_path}")

            logger.info("📊 Extracting bank exchange rate data...")
            bank_data = []

            all_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Bank') or contains(text(), 'HSBC')]")
            logger.info(f"🔍 Found {len(all_elements)} potential bank elements")

            for element in all_elements:
                try:
                    element_text = element.text.strip()
                    if element_text and len(element_text) > 10:

                        bank_names = ['Central Bank of Sri Lanka', 'Amana Bank', 'Bank of Ceylon',
                                      'Commercial Bank', 'Hatton National Bank', 'HSBC Bank',
                                      'Nations Trust Bank', "People's Bank", 'Sampath Bank']

                        for bank_name in bank_names:
                            if bank_name.lower() in element_text.lower():
                                numbers = re.findall(r'\d+\.\d+', element_text)

                                if len(numbers) < 2:
                                    try:
                                        parent_text = element.find_element(By.XPATH, "..").text
                                        numbers.extend(re.findall(r'\d+\.\d+', parent_text))
                                    except:
                                        pass

                                valid_rates = [float(num) for num in numbers if 100 <= float(num) <= 250]

                                if len(valid_rates) >= 2:
                                    normalized_bank_name = normalize_bank_name(bank_name)

                                    # Check for duplicates
                                    duplicate_found = False
                                    for existing_bank in bank_data:
                                        if existing_bank['bank'] == normalized_bank_name:
                                            duplicate_found = True
                                            break

                                    if not duplicate_found:
                                        bank_info = {
                                            'bank': normalized_bank_name,
                                            'buying_rate': valid_rates[1],
                                            'selling_rate': valid_rates[0],
                                            'currency': 'AUD',
                                            'source': 'numbers.lk',
                                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                            'source_url': url
                                        }
                                        bank_data.append(bank_info)
                                        logger.info(f"✅ Found: {normalized_bank_name} - Buy: {valid_rates[1]}, Sell: {valid_rates[0]}")
                                        break

                except Exception as e:
                    continue

            # If we don't have enough banks, try comprehensive parsing
            if len(bank_data) < 8:
                logger.info(f"⚠️ Only found {len(bank_data)} banks, trying comprehensive parsing...")
                page_source = driver.page_source

                bank_patterns = [
                    (r'Central Bank of Sri Lanka.*?(\d+\.\d+).*?(\d+\.\d+)', 'Central Bank of Sri Lanka'),
                    (r'Amana Bank.*?(\d+\.\d+).*?(\d+\.\d+)', 'Amana Bank'),
                    (r'Bank of Ceylon.*?(\d+\.\d+).*?(\d+\.\d+)', 'Bank of Ceylon'),
                    (r'Commercial Bank.*?(\d+\.\d+).*?(\d+\.\d+)', 'Commercial Bank'),
                    (r'Hatton National Bank.*?(\d+\.\d+).*?(\d+\.\d+)', 'Hatton National Bank'),
                    (r'HSBC.*?Bank.*?(\d+\.\d+).*?(\d+\.\d+)', 'HSBC Bank'),
                    (r'HSBC.*?(\d+\.\d+).*?(\d+\.\d+)', 'HSBC Bank'),
                    (r'Nations Trust Bank.*?(\d+\.\d+).*?(\d+\.\d+)', 'Nations Trust Bank'),
                    (r'People\'s Bank.*?(\d+\.\d+).*?(\d+\.\d+)', "People's Bank"),
                    (r'Peoples Bank.*?(\d+\.\d+).*?(\d+\.\d+)', "People's Bank"),
                    (r'Sampath Bank.*?(\d+\.\d+).*?(\d+\.\d+)', 'Sampath Bank')
                ]

                for pattern, bank_name in bank_patterns:
                    matches = re.findall(pattern, page_source, re.IGNORECASE | re.DOTALL)
                    if matches:
                        for match in matches:
                            rate1, rate2 = match
                            normalized_bank_name = normalize_bank_name(bank_name)

                            # Check for duplicates
                            duplicate_found = False
                            for existing_bank in bank_data:
                                if existing_bank['bank'] == normalized_bank_name:
                                    duplicate_found = True
                                    break

                            if not duplicate_found and 100 <= float(rate1) <= 250 and 100 <= float(rate2) <= 250:
                                bank_info = {
                                    'bank': normalized_bank_name,
                                    'buying_rate': float(rate2),
                                    'selling_rate': float(rate1),
                                    'currency': 'AUD',
                                    'source': 'numbers.lk',
                                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'source_url': url
                                }
                                bank_data.append(bank_info)
                                logger.info(f"✅ Pattern match: {normalized_bank_name} - Buy: {rate2}, Sell: {rate1}")
                                break

            logger.info(f"📊 numbers.lk scraping completed. Found {len(bank_data)} banks")
            return bank_data

        finally:
            if driver:
                driver.quit()

    except (NameError, ImportError):
        logger.error("❌ Selenium not installed")
        return []
    except Exception as e:
        logger.error(f"❌ Error scraping numbers.lk: {e}")
        return []

def enhance_with_direct_ntb_scraping(bank_data_list, logger, screenshots_dir):
    """Enhanced NTB scraping with comprehensive logging"""

    # Check if NTB exists
    ntb_found = False
    ntb_index = -1

    for idx, bank in enumerate(bank_data_list):
        if 'nations trust' in bank['bank'].lower() or 'ntb' in bank['bank'].lower():
            ntb_found = True
            ntb_index = idx
            break

    if ntb_found:
        logger.info(f"📝 NTB found in numbers.lk data: {bank_data_list[ntb_index]['bank']}")
        logger.info(f"   Buy: {bank_data_list[ntb_index]['buying_rate']}, Sell: {bank_data_list[ntb_index]['selling_rate']}")
        logger.info("🔄 Attempting direct NTB scraping for verification...")
    else:
        logger.info("❌ NTB not found in numbers.lk data. Attempting direct scraping...")

    # Try direct NTB scraping
    logger.info("🏦 Attempting direct NTB scraping...")
    ntb_direct_data = scrape_ntb_aud_rates(logger)

    if not ntb_direct_data or ntb_direct_data['buying_rate'] is None:
        logger.info("⚠️ Primary NTB method failed. Trying Selenium...")
        ntb_direct_data = scrape_ntb_with_selenium(logger, screenshots_dir)

    if ntb_direct_data and ntb_direct_data['buying_rate'] is not None:
        logger.info(f"✅ Direct NTB scraping successful!")
        logger.info(f"   Buy: {ntb_direct_data['buying_rate']}, Sell: {ntb_direct_data['selling_rate']}")

        if ntb_found:
            # Compare and use direct data
            existing_ntb = bank_data_list[ntb_index]
            logger.info(f"📊 Comparing NTB rates:")
            logger.info(f"   numbers.lk: Buy {existing_ntb['buying_rate']}, Sell {existing_ntb['selling_rate']}")
            logger.info(f"   Direct:     Buy {ntb_direct_data['buying_rate']}, Sell {ntb_direct_data['selling_rate']}")

            bank_data_list[ntb_index] = ntb_direct_data
            logger.info("✅ Using direct NTB data (more reliable)")
        else:
            bank_data_list.append(ntb_direct_data)
            logger.info("✅ Added direct NTB data to bank list")
    else:
        logger.error("❌ All NTB scraping methods failed")
        if not ntb_found:
            logger.warning("⚠️ NTB will be missing from final data")

    return bank_data_list

# --- HNB Scraping Functions ---

def scrape_hnb_aud_rates(logger, screenshots_dir):
    """
    Scrape AUD exchange rates from HNB website using Selenium
    Returns: Dictionary containing AUD buying and selling rates
    """
    url = "https://www.hnb.lk/"
    aud_data = {
        'bank': 'Hatton National Bank',
        'currency': 'AUD',
        'buying_rate': None,
        'selling_rate': None,
        'source': 'HNB Direct',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_url': url
    }
    driver = None

    try:
        # Setup Chrome driver
        driver = setup_selenium_for_github_actions()
        if not driver:
            return aud_data # Return empty data structure

        logger.info("🌐 Loading HNB website...")
        driver.get(url)

        # Wait for page to load
        wait = WebDriverWait(driver, 20)

        # Strategy 1: Wait for exchange rate section to load and look for AUD
        try:
            logger.info(" HNB Strategy 1: Looking for exchange rate elements...")
            wait.until(
                EC.presence_of_all_elements_located((By.XPATH, "//*[contains(text(), 'USD') or contains(text(), 'Exchange') or contains(text(), 'Rate')]"))
            )
            time.sleep(5) # Give extra time for all rates to load

            aud_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'AUS') or contains(text(), 'AUD')]")
            for element in aud_elements:
                logger.info(f"  Found potential AUD element: {element.text[:100]}")
                parent = element
                for _ in range(5):  # Check up to 5 parent levels
                    try:
                        parent_text = parent.text
                        numbers = re.findall(r'(\d{2,3}\.\d{1,4})', parent_text)
                        valid_rates = [float(num) for num in numbers if 100 <= float(num) <= 250]

                        if len(valid_rates) >= 2:
                            valid_rates.sort()
                            aud_data['buying_rate'] = valid_rates[0]
                            aud_data['selling_rate'] = valid_rates[1]
                            logger.info(f"  Found rates in parent - Buying: {valid_rates[0]}, Selling: {valid_rates[1]}")
                            return aud_data
                        parent = parent.find_element(By.XPATH, "..")
                    except:
                        break
        except TimeoutException:
            logger.warning(" HNB Strategy 1 failed - no exchange rate elements found")

        # Strategy 2: Search entire page source for AUD rates
        try:
            logger.info(" HNB Strategy 2: Searching page source...")
            page_source = driver.page_source
            aud_pattern = r'(?i)(?:AUD|AUS|Australian).*?(\d{2,3}\.\d{1,4}).*?(\d{2,3}\.\d{1,4})'
            matches = re.findall(aud_pattern, page_source)

            for match in matches:
                rates = [float(rate) for rate in match if 100 <= float(rate) <= 250]
                if len(rates) >= 2:
                    rates.sort()
                    aud_data['buying_rate'] = rates[0]
                    aud_data['selling_rate'] = rates[1]
                    logger.info(f"  Found rates in page source - Buying: {rates[0]}, Selling: {rates[1]}")
                    return aud_data
        except Exception as e:
            logger.warning(f" HNB Strategy 2 failed: {e}")

        # Strategy 3: Take screenshot for manual inspection
        try:
            screenshot_path = screenshots_dir / f"hnb_debug_{datetime.now().strftime('%H%M%S')}.png"
            driver.save_screenshot(str(screenshot_path))
            logger.info(f"📸 HNB screenshot saved for debugging: {screenshot_path}")
        except:
            pass

        logger.warning(" All HNB direct scraping strategies failed.")
        return aud_data

    except WebDriverException as e:
        logger.error(f"❌ WebDriver error during HNB scraping: {e}")
        return aud_data
    except Exception as e:
        logger.error(f"❌ Unhandled error scraping HNB data: {e}")
        return aud_data
    finally:
        if driver:
            driver.quit()

def enhance_with_direct_hnb_scraping(bank_data_list, logger, screenshots_dir):
    """Enhanced HNB scraping with comprehensive logging"""

    hnb_found = False
    hnb_index = -1
    for idx, bank in enumerate(bank_data_list):
        if 'hatton national' in bank['bank'].lower() or 'hnb' in bank['bank'].lower():
            hnb_found = True
            hnb_index = idx
            break

    if hnb_found:
        logger.info(f"📝 HNB found in numbers.lk data: {bank_data_list[hnb_index]['bank']}")
        logger.info(f"   Buy: {bank_data_list[hnb_index]['buying_rate']}, Sell: {bank_data_list[hnb_index]['selling_rate']}")
        logger.info("🔄 Attempting direct HNB scraping for verification...")
    else:
        logger.info("❌ HNB not found in numbers.lk data. Attempting direct scraping...")

    # Attempt direct scraping
    hnb_direct_data = scrape_hnb_aud_rates(logger, screenshots_dir)

    if hnb_direct_data and hnb_direct_data.get('buying_rate') is not None:
        logger.info("✅ Direct HNB scraping successful!")
        logger.info(f"   Buy: {hnb_direct_data['buying_rate']}, Sell: {hnb_direct_data['selling_rate']}")

        # Create a full bank data dictionary
        full_hnb_data = {
            'bank': normalize_bank_name('Hatton National Bank'),
            'buying_rate': hnb_direct_data['buying_rate'],
            'selling_rate': hnb_direct_data['selling_rate'],
            'currency': 'AUD',
            'source': hnb_direct_data['source'],
            'timestamp': hnb_direct_data['timestamp'],
            'source_url': hnb_direct_data['source_url']
        }

        if hnb_found:
            existing_hnb = bank_data_list[hnb_index]
            logger.info("📊 Comparing HNB rates:")
            logger.info(f"   numbers.lk: Buy {existing_hnb['buying_rate']}, Sell {existing_hnb['selling_rate']}")
            logger.info(f"   Direct:     Buy {full_hnb_data['buying_rate']}, Sell {full_hnb_data['selling_rate']}")
            bank_data_list[hnb_index] = full_hnb_data
            logger.info("✅ Using direct HNB data (more reliable)")
        else:
            bank_data_list.append(full_hnb_data)
            logger.info("✅ Added direct HNB data to bank list")
    else:
        logger.error("❌ Direct HNB scraping failed to retrieve rates.")
        if not hnb_found:
            logger.warning("⚠️ HNB will be missing from final data")

    return bank_data_list

def create_execution_summary(bank_data_list, logger):
    """Create execution summary for GitHub Actions"""

    summary_data = {
        'execution_time': datetime.now().isoformat(),
        'total_banks_scraped': len(bank_data_list),
        'banks_list': [bank['bank'] for bank in bank_data_list],
        'sources_used': list(set(bank.get('source', 'numbers.lk') for bank in bank_data_list)),
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
            'best_rate_to_sell_aud': {
                'bank': best_selling_bank['bank'],
                'rate': best_selling_bank['buying_rate']
            },
            'best_rate_to_buy_aud': {
                'bank': best_buying_bank['bank'],
                'rate': best_buying_bank['selling_rate']
            },
            'average_buying_rate': sum(bank['buying_rate'] for bank in bank_data_list) / len(bank_data_list),
            'average_selling_rate': sum(bank['selling_rate'] for bank in bank_data_list) / len(bank_data_list)
        })

    # Save summary to file for GitHub Actions artifacts
    summary_file = Path("execution_summary.json")
    with open(summary_file, 'w') as f:
        json.dump(summary_data, f, indent=2, default=str)

    logger.info(f"📋 Execution summary saved to {summary_file}")
    return summary_data

def print_bank_rates_workflow_friendly(bank_data_list, logger):
    """Print bank rates optimized for GitHub Actions logs"""
    if not bank_data_list:
        logger.error("❌ No bank data found")
        return

    logger.info("=" * 80)
    logger.info("🏦 ALL BANKS - AUD EXCHANGE RATES (People's Perspective)")
    logger.info("=" * 80)

    for bank_info in bank_data_list:
        spread = bank_info['selling_rate'] - bank_info['buying_rate']
        source_indicator = "🌐" if 'numbers.lk' in bank_info.get('source', '') else "🏦"
        logger.info(f"{source_indicator} {bank_info['bank']} [{bank_info.get('source', 'N/A')}]")
        logger.info(f"   💰 Sell AUD For: LKR {bank_info['buying_rate']:.2f}")
        logger.info(f"   💸 Buy AUD For:  LKR {bank_info['selling_rate']:.2f}")
        logger.info(f"   📊 Spread:       LKR {spread:.4f}")
        logger.info("-" * 50)

    # Show best rates
    best_selling_bank = max(bank_data_list, key=lambda x: x['buying_rate'])
    best_buying_bank = min(bank_data_list, key=lambda x: x['selling_rate'])

    logger.info("🎯 BEST RATES FOR YOU:")
    logger.info(f"✅ Best to Sell AUD: LKR {best_selling_bank['buying_rate']:.2f} at {best_selling_bank['bank']}")
    logger.info(f"✅ Best to Buy AUD:  LKR {best_buying_bank['selling_rate']:.2f} at {best_buying_bank['bank']}")
    logger.info(f"📈 Total Banks: {len(bank_data_list)}")

    # Show data sources
    sources = {}
    for bank in bank_data_list:
        source = bank.get('source', 'numbers.lk')
        sources[source] = sources.get(source, 0) + 1

    logger.info(f"📡 Data Sources: {dict(sources)}")
    logger.info("=" * 80)

def main():
    """Main execution function optimized for GitHub Actions"""

    # Setup logging and environment
    logger = setup_logging()
    log_environment_info(logger)
    screenshots_dir = create_screenshots_dir()

    # Initialize variables
    db = None
    exit_code = 0

    try:
        logger.info("🔗 Connecting to MongoDB Atlas...")
        db = ExchangeRateDB(logger=logger)

        # Step 1: Scrape from numbers.lk
        logger.info("📡 Step 1: Scraping from numbers.lk...")
        all_bank_data = scrape_numbers_lk_aud_rates(logger, screenshots_dir)

        if all_bank_data:
            logger.info(f"✅ numbers.lk returned {len(all_bank_data)} banks")
        else:
            logger.warning("⚠️ numbers.lk scraping failed or returned no data. Proceeding with direct scraping.")
            all_bank_data = []

        # Step 2: Enhance with direct NTB scraping
        logger.info("🏦 Step 2: Enhancing with direct NTB scraping...")
        all_bank_data = enhance_with_direct_ntb_scraping(all_bank_data, logger, screenshots_dir)

        # Step 3: Enhance with direct HNB scraping
        logger.info("🏦 Step 3: Enhancing with direct HNB scraping...")
        all_bank_data = enhance_with_direct_hnb_scraping(all_bank_data, logger, screenshots_dir)

        # Step 4: Display and save results
        if all_bank_data:
            print_bank_rates_workflow_friendly(all_bank_data, logger)

            # Save to MongoDB
            success = db.upsert_daily_rates(all_bank_data)

            if success:
                logger.info(f"🎉 [SUCCESS] Saved {len(all_bank_data)} banks to MongoDB Atlas")
                bank_names = [bank['bank'] for bank in all_bank_data]
                logger.info(f"🏦 Banks: {', '.join(bank_names)}")

                # Show today's complete data
                today_data = db.get_daily_rates()
                if today_data:
                    logger.info(f"📊 Today's document contains {today_data['total_banks']} banks")
                    stats = today_data['market_statistics']
                    logger.info(f"🟢 Best Sell Rate: {stats['people_selling']['best_bank']} (LKR {stats['people_selling']['max']})")
                    logger.info(f"🔵 Best Buy Rate: {stats['people_buying']['best_bank']} (LKR {stats['people_buying']['min']})")

                    # Show direct scraped banks
                    direct_scraped = [bank['bank'] for bank in all_bank_data if 'Direct' in bank.get('source', '') or 'Selenium' in bank.get('source', '')]
                    if direct_scraped:
                        logger.info(f"🏦 Directly Verified: {', '.join(direct_scraped)}")

                # Create execution summary
                create_execution_summary(all_bank_data, logger)
                logger.info("✨ Execution completed successfully!")

            else:
                logger.error("❌ [ERROR] Failed to save data to MongoDB Atlas")
                exit_code = 1
        else:
            logger.error("❌ [ERROR] Failed to scrape any bank data from any source")
            logger.error("Possible causes:")
            logger.error("1. Website structure changes on all target sites")
            logger.error("2. Network connectivity issues or IP blocking")
            logger.error("3. ChromeDriver/Selenium setup issues in the environment")
            logger.error("4. JavaScript-heavy sites preventing content loading")
            exit_code = 1

    except Exception as e:
        logger.error(f"❌ Critical error in main execution: {e}")
        logger.error("Please check:")
        logger.error("1. MONGODB_CONNECTION_STRING secret is set")
        logger.error("2. Internet connectivity")
        logger.error("3. MongoDB Atlas cluster status")
        logger.error("4. Chrome/ChromeDriver installation (if running locally)")
        exit_code = 1

        # Log full traceback for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

    finally:
        # Cleanup
        if db:
            db.close_connection()

        # Log final execution status
        if exit_code == 0:
            logger.info("🏁 Script execution completed successfully")
        else:
            logger.error("🏁 Script execution failed")

        # Exit with appropriate code for GitHub Actions
        sys.exit(exit_code)

if __name__ == "__main__":
    main()