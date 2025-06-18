#!/usr/bin/env python3
"""
GitHub Workflow-Friendly EUR Exchange Rate Scraper
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
    log_file = log_dir / f"eur_exchange_scraper_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)  # For GitHub Actions console
        ]
    )
    
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

class EURExchangeRateDB:
    """MongoDB handler optimized for GitHub Actions execution - EUR collection"""
    
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
            self.collection = self.db.daily_eur_rates  # EUR collection
            
            # Create index on date for faster queries
            self.collection.create_index([("date", ASCENDING)], unique=True)
            
            # Test connection
            self.client.admin.command('ping')
            self.logger.info(f"✅ Connected to MongoDB Atlas database: {db_name} (EUR collection)")
            
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
            'people_selling': {  # People selling EUR (bank buying)
                'min': min(buying_rates),  # Worst rate for people
                'max': max(buying_rates),  # Best rate for people
                'avg': sum(buying_rates) / len(buying_rates),
                'best_bank': max(bank_data_list, key=lambda x: x['buying_rate'])['bank']
            },
            'people_buying': {  # People buying EUR (bank selling)
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
            'currency': 'EUR',
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
                self.logger.info(f"📝 Found existing EUR document for {current_date}. Updating...")
                
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
                self.logger.info(f"✅ Updated EUR document for {current_date}")
                self.logger.info(f"📊 Previous banks: {list(existing_banks.keys())}")
                self.logger.info(f"🔄 Updated banks: {list(new_banks.keys())}")
                self.logger.info(f"📈 Total banks now: {len(merged_banks)}")
                
            else:
                # Insert new document
                result = self.collection.insert_one(new_document)
                self.logger.info(f"🆕 Created new EUR document for {current_date}")
                self.logger.info(f"📊 Banks added: {list(new_document['bank_rates'].keys())}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error saving EUR data to MongoDB Atlas: {e}")
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
    """Setup Selenium WebDriver optimized for GitHub Actions"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        
        # Chrome options optimized for GitHub Actions
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
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
        
        return chrome_options
        
    except ImportError as e:
        logging.error(f"❌ Selenium not available: {e}")
        return None

def scrape_ntb_eur_rates(logger):
    """
    Scrape EUR exchange rates directly from NTB with enhanced error handling
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
        logger.info("🌐 Scraping NTB directly for EUR rates...")
        
        # Send GET request with timeout
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        eur_data = {
            'bank': 'Nations Trust Bank',
            'currency': 'EUR',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'NTB Direct',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }
        
        # Check if EUR data exists
        page_text = soup.get_text()
        if 'EUR' not in page_text:
            logger.warning("❌ EUR not found in NTB page content")
            return None
        
        # Try to find EUR in tables
        tables = soup.find_all('table')
        logger.info(f"🔍 Found {len(tables)} tables on NTB page")
        
        for table_idx, table in enumerate(tables):
            rows = table.find_all('tr')
            
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]
                
                # Look for EUR in the row
                if any('EUR' in cell for cell in row_text):
                    logger.info(f"✅ Found EUR in NTB table {table_idx + 1}, row {row_idx + 1}")
                    
                    # Extract numeric values
                    numeric_values = []
                    for cell in row_text:
                        clean_cell = cell.replace(',', '').replace(' ', '')
                        numbers = re.findall(r'\d+\.\d+', clean_cell)
                        for num in numbers:
                            if 250 <= float(num) <= 550:  # EUR rates are usually 250-550 LKR
                                numeric_values.append(float(num))
                    
                    logger.info(f"📊 NTB EUR numeric values found: {numeric_values}")
                    
                    if len(numeric_values) >= 2:
                        eur_data['buying_rate'] = numeric_values[0]
                        eur_data['selling_rate'] = numeric_values[1]
                        logger.info(f"✅ NTB EUR Direct - Buy: {numeric_values[0]}, Sell: {numeric_values[1]}")
                        return eur_data
        
        logger.warning("❌ No EUR rates found in NTB tables")
        return None
        
    except requests.RequestException as e:
        logger.error(f"❌ Error fetching NTB webpage: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Error parsing NTB EUR data: {e}")
        return None

def scrape_ntb_eur_with_selenium(logger, screenshots_dir):
    """
    Selenium-based NTB EUR scraping with screenshot capture for debugging
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        logger.info("🚀 Trying NTB EUR with Selenium WebDriver...")
        
        chrome_options = setup_selenium_for_github_actions()
        if not chrome_options:
            return None
        
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            logger.info("🌐 Loading NTB page with Selenium for EUR...")
            driver.get("https://www.nationstrust.com/foreign-exchange-rates")
            
            # Take screenshot for debugging
            screenshot_path = screenshots_dir / f"ntb_eur_page_{datetime.now().strftime('%H%M%S')}.png"
            driver.save_screenshot(str(screenshot_path))
            logger.info(f"📸 EUR Screenshot saved: {screenshot_path}")
            
            # Wait for page to load
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            
            time.sleep(3)  # Additional wait for dynamic content
            
            # Check for EUR
            page_source = driver.page_source
            if 'EUR' not in page_source:
                logger.warning("❌ EUR not found in Selenium page source")
                return None
            
            # Find EUR data
            rows = driver.find_elements(By.TAG_NAME, "tr")
            logger.info(f"🔍 Selenium found {len(rows)} total rows")
            
            for row_idx, row in enumerate(rows):
                row_text = row.text.strip()
                if 'EUR' in row_text:
                    logger.info(f"✅ Found EUR row {row_idx + 1}: {row_text[:100]}...")
                    
                    # Extract rates
                    numbers = re.findall(r'\d+\.\d+', row_text.replace(',', ''))
                    exchange_rates = [float(num) for num in numbers if 250 <= float(num) <= 550]
                    
                    logger.info(f"📊 NTB Selenium EUR rates: {exchange_rates}")
                    
                    if len(exchange_rates) >= 2:
                        return {
                            'bank': 'Nations Trust Bank',
                            'currency': 'EUR',
                            'buying_rate': exchange_rates[0],
                            'selling_rate': exchange_rates[1],
                            'source': 'NTB Selenium',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': "https://www.nationstrust.com/foreign-exchange-rates"
                        }
            
            logger.warning("❌ No EUR rates found with Selenium")
            return None
            
        finally:
            driver.quit()
            
    except ImportError:
        logger.error("❌ Selenium not installed")
        return None
    except Exception as e:
        logger.error(f"❌ Selenium scraping error for NTB EUR: {e}")
        return None

def scrape_numbers_lk_eur_rates(logger, screenshots_dir):
    """Scrape all EUR exchange rates from numbers.lk with enhanced logging"""
    url = "https://tools.numbers.lk/exrates"
    
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        
        logger.info("🚀 Setting up Selenium driver for numbers.lk EUR...")
        
        chrome_options = setup_selenium_for_github_actions()
        if not chrome_options:
            return []
        
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            logger.info("🌐 Loading numbers.lk exchange rates page for EUR...")
            driver.get(url)
            
            # Take screenshot for debugging
            screenshot_path = screenshots_dir / f"numbers_lk_eur_initial_{datetime.now().strftime('%H%M%S')}.png"
            driver.save_screenshot(str(screenshot_path))
            logger.info(f"📸 EUR Initial screenshot saved: {screenshot_path}")
            
            time.sleep(3)
            
            logger.info("🔍 Looking for EUR currency option...")
            
            # Try different selectors to find EUR
            eur_selectors = [
                "//div[contains(text(), 'EUR')]",
                "//span[contains(text(), 'EUR')]", 
                "//button[contains(text(), 'EUR')]",
                "//a[contains(text(), 'EUR')]",
                "//*[contains(text(), 'EUR')]"
            ]
            
            eur_element = None
            for selector in eur_selectors:
                try:
                    eur_element = driver.find_element(By.XPATH, selector)
                    logger.info(f"✅ Found EUR element with selector: {selector}")
                    break
                except:
                    continue
            
            if eur_element:
                driver.execute_script("arguments[0].click();", eur_element)
                logger.info("🖱️ Clicked on EUR currency")
                time.sleep(5)
                
                # Take screenshot after clicking
                screenshot_path = screenshots_dir / f"numbers_lk_eur_after_click_{datetime.now().strftime('%H%M%S')}.png"
                driver.save_screenshot(str(screenshot_path))
                logger.info(f"📸 EUR Post-click screenshot saved: {screenshot_path}")
            
            logger.info("📊 Extracting bank EUR exchange rate data...")
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
                                
                                valid_rates = [float(num) for num in numbers if 250 <= float(num) <= 550]  # EUR rate range
                                
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
                                            'currency': 'EUR',
                                            'source': 'numbers.lk',
                                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                            'source_url': url
                                        }
                                        bank_data.append(bank_info)
                                        logger.info(f"✅ Found EUR: {normalized_bank_name} - Buy: {valid_rates[1]}, Sell: {valid_rates[0]}")
                                        break
                                
                except Exception as e:
                    continue
            
            # If we don't have enough banks, try comprehensive parsing
            if len(bank_data) < 8:
                logger.info(f"⚠️ Only found {len(bank_data)} banks, trying comprehensive EUR parsing...")
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
                            
                            if not duplicate_found and 250 <= float(rate1) <= 550 and 250 <= float(rate2) <= 550:
                                bank_info = {
                                    'bank': normalized_bank_name,
                                    'buying_rate': float(rate2),
                                    'selling_rate': float(rate1),
                                    'currency': 'EUR',
                                    'source': 'numbers.lk',
                                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'source_url': url
                                }
                                bank_data.append(bank_info)
                                logger.info(f"✅ EUR Pattern match: {normalized_bank_name} - Buy: {rate2}, Sell: {rate1}")
                                break
            
            logger.info(f"📊 numbers.lk EUR scraping completed. Found {len(bank_data)} banks")
            return bank_data
            
        finally:
            driver.quit()
            
    except ImportError:
        logger.error("❌ Selenium not installed")
        return []
    except Exception as e:
        logger.error(f"❌ Error scraping numbers.lk EUR: {e}")
        return []

def enhance_with_direct_ntb_eur_scraping(bank_data_list, logger, screenshots_dir):
    """Enhanced NTB EUR scraping with comprehensive logging"""
    
    # Check if NTB exists
    ntb_found = False
    ntb_index = -1
    
    for idx, bank in enumerate(bank_data_list):
        if 'nations trust' in bank['bank'].lower() or 'ntb' in bank['bank'].lower():
            ntb_found = True
            ntb_index = idx
            break
    
    if ntb_found:
        logger.info(f"📝 NTB found in numbers.lk EUR data: {bank_data_list[ntb_index]['bank']}")
        logger.info(f"   Buy: {bank_data_list[ntb_index]['buying_rate']}, Sell: {bank_data_list[ntb_index]['selling_rate']}")
        logger.info("🔄 Attempting direct NTB EUR scraping for verification...")
    else:
        logger.info("❌ NTB not found in numbers.lk EUR data. Attempting direct scraping...")
    
    # Try direct NTB EUR scraping
    logger.info("🏦 Attempting direct NTB EUR scraping...")
    ntb_direct_data = scrape_ntb_eur_rates(logger)
    
    if not ntb_direct_data or ntb_direct_data['buying_rate'] is None:
        logger.info("⚠️ Primary NTB EUR method failed. Trying Selenium...")
        ntb_direct_data = scrape_ntb_eur_with_selenium(logger, screenshots_dir)
    
    if ntb_direct_data and ntb_direct_data['buying_rate'] is not None:
        logger.info(f"✅ Direct NTB EUR scraping successful!")
        logger.info(f"   Buy: {ntb_direct_data['buying_rate']}, Sell: {ntb_direct_data['selling_rate']}")
        
        if ntb_found:
            # Compare and use direct data
            existing_ntb = bank_data_list[ntb_index]
            logger.info(f"📊 Comparing NTB EUR rates:")
            logger.info(f"   numbers.lk: Buy {existing_ntb['buying_rate']}, Sell {existing_ntb['selling_rate']}")
            logger.info(f"   Direct:     Buy {ntb_direct_data['buying_rate']}, Sell {ntb_direct_data['selling_rate']}")
            
            bank_data_list[ntb_index] = ntb_direct_data
            logger.info("✅ Using direct NTB EUR data (more reliable)")
        else:
            bank_data_list.append(ntb_direct_data)
            logger.info("✅ Added direct NTB EUR data to bank list")
    else:
        logger.error("❌ All NTB EUR scraping methods failed")
        if not ntb_found:
            logger.warning("⚠️ NTB will be missing from final EUR data")
    
    return bank_data_list

def create_execution_summary(bank_data_list, logger):
    """Create execution summary for GitHub Actions"""
    
    summary_data = {
        'execution_time': datetime.now().isoformat(),
        'currency': 'EUR',
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
            'best_rate_to_sell_eur': {
                'bank': best_selling_bank['bank'],
                'rate': best_selling_bank['buying_rate']
            },
            'best_rate_to_buy_eur': {
                'bank': best_buying_bank['bank'],
                'rate': best_buying_bank['selling_rate']
            },
            'average_buying_rate': sum(bank['buying_rate'] for bank in bank_data_list) / len(bank_data_list),
            'average_selling_rate': sum(bank['selling_rate'] for bank in bank_data_list) / len(bank_data_list)
        })
    
    # Save summary to file for GitHub Actions artifacts
    summary_file = Path("eur_execution_summary.json")
    with open(summary_file, 'w') as f:
        json.dump(summary_data, f, indent=2, default=str)
    
    logger.info(f"📋 EUR Execution summary saved to {summary_file}")
    return summary_data

def print_bank_rates_workflow_friendly(bank_data_list, logger):
    """Print bank rates optimized for GitHub Actions logs"""
    if not bank_data_list:
        logger.error("❌ No EUR bank data found")
        return
    
    logger.info("=" * 80)
    logger.info("🏦 ALL BANKS - EUR EXCHANGE RATES (People's Perspective)")
    logger.info("=" * 80)
    
    for bank_info in bank_data_list:
        spread = bank_info['selling_rate'] - bank_info['buying_rate']
        source_indicator = "🌐" if bank_info.get('source') == 'numbers.lk' else "🏦"
        logger.info(f"{source_indicator} {bank_info['bank']} [{bank_info.get('source', 'numbers.lk')}]")
        logger.info(f"   💰 Sell EUR For: LKR {bank_info['buying_rate']}")
        logger.info(f"   💸 Buy EUR For: LKR {bank_info['selling_rate']}")
        logger.info(f"   📊 Spread: LKR {spread:.4f}")
        logger.info("-" * 50)
    
    # Show best rates
    best_selling_bank = max(bank_data_list, key=lambda x: x['buying_rate'])
    best_buying_bank = min(bank_data_list, key=lambda x: x['selling_rate'])
    
    logger.info("🎯 BEST EUR RATES FOR YOU:")
    logger.info(f"✅ Best to Sell EUR: LKR {best_selling_bank['buying_rate']} at {best_selling_bank['bank']}")
    logger.info(f"✅ Best to Buy EUR: LKR {best_buying_bank['selling_rate']} at {best_buying_bank['bank']}")
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
        logger.info("🔗 Connecting to MongoDB Atlas for EUR data...")
        db = EURExchangeRateDB(logger=logger)
        
        # Step 1: Scrape from numbers.lk
        logger.info("📡 Step 1: Scraping EUR from numbers.lk...")
        numbers_lk_data = scrape_numbers_lk_eur_rates(logger, screenshots_dir)
        
        if numbers_lk_data:
            logger.info(f"✅ numbers.lk returned {len(numbers_lk_data)} EUR banks")
        else:
            logger.warning("❌ numbers.lk EUR scraping failed")
            numbers_lk_data = []
        
        # Step 2: Enhance with direct NTB scraping
        logger.info("🏦 Step 2: Enhancing with direct NTB EUR scraping...")
        enhanced_bank_data = enhance_with_direct_ntb_eur_scraping(numbers_lk_data, logger, screenshots_dir)
        
        # Step 3: Display and save results
        if enhanced_bank_data:
            print_bank_rates_workflow_friendly(enhanced_bank_data, logger)
            
            # Save to MongoDB
            success = db.upsert_daily_rates(enhanced_bank_data)
            
            if success:
                logger.info(f"🎉 [SUCCESS] Saved {len(enhanced_bank_data)} EUR banks to MongoDB Atlas")
                bank_names = [bank['bank'] for bank in enhanced_bank_data]
                logger.info(f"🏦 EUR Banks: {', '.join(bank_names)}")
                
                # Show today's complete data
                today_data = db.get_daily_rates()
                if today_data:
                    logger.info(f"📊 Today's EUR document contains {today_data['total_banks']} banks")
                    stats = today_data['market_statistics']
                    logger.info(f"🟢 Best EUR Sell Rate: {stats['people_selling']['best_bank']} (LKR {stats['people_selling']['max']})")
                    logger.info(f"🔵 Best EUR Buy Rate: {stats['people_buying']['best_bank']} (LKR {stats['people_buying']['min']})")
                    
                    # Show direct scraped banks
                    direct_scraped = [bank for bank in enhanced_bank_data if bank.get('source') != 'numbers.lk']
                    if direct_scraped:
                        logger.info(f"🏦 Direct EUR Scraped: {', '.join([bank['bank'] for bank in direct_scraped])}")
                
                # Create execution summary
                create_execution_summary(enhanced_bank_data, logger)
                logger.info("✨ EUR Execution completed successfully!")
                
            else:
                logger.error("❌ [ERROR] Failed to save EUR data to MongoDB Atlas")
                exit_code = 1
        else:
            logger.error("❌ [ERROR] Failed to scrape any EUR bank data")
            logger.error("Possible causes:")
            logger.error("1. Website structure changes")
            logger.error("2. Network connectivity issues")
            logger.error("3. ChromeDriver/Selenium issues")
            logger.error("4. JavaScript loading problems")
            exit_code = 1
        
    except Exception as e:
        logger.error(f"❌ Critical EUR scraping error: {e}")
        logger.error("Please check:")
        logger.error("1. MONGODB_CONNECTION_STRING secret is set")
        logger.error("2. Internet connectivity")
        logger.error("3. MongoDB Atlas cluster status")
        logger.error("4. Chrome/ChromeDriver installation")
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
            logger.info("🏁 EUR Script execution completed successfully")
        else:
            logger.error("🏁 EUR Script execution failed")
        
        # Exit with appropriate code for GitHub Actions
        sys.exit(exit_code)

if __name__ == "__main__":
    main()