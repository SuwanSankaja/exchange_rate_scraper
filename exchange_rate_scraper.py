import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
import time
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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
    """MongoDB handler for exchange rate data with visualization-optimized structure"""
    
    def __init__(self, connection_string=None, db_name="exchange_rates"):
        if connection_string is None:
            connection_string = os.getenv('MONGODB_CONNECTION_STRING')
        
        if not connection_string:
            raise ValueError("MongoDB connection string not provided. Set MONGODB_CONNECTION_STRING environment variable.")
        
        try:
            self.client = MongoClient(connection_string)
            self.db = self.client[db_name]
            self.collection = self.db.daily_rates
            
            # Create index on date for faster queries
            self.collection.create_index([("date", ASCENDING)], unique=True)
            
            # Test connection
            self.client.admin.command('ping')
            print(f"✅ Connected to MongoDB Atlas database: {db_name}")
            
        except ConnectionFailure:
            print("❌ Failed to connect to MongoDB Atlas. Check your connection string and network.")
            raise
        except Exception as e:
            print(f"❌ MongoDB connection error: {e}")
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
            'data_completeness': {
                'banks_updated': list(bank_rates.keys()),
                'banks_count': len(bank_rates),
                'update_timestamp': current_datetime
            }
        }
        
        return document
    
    def upsert_daily_rates(self, bank_data_list):
        """Insert or update daily exchange rates"""
        if not bank_data_list:
            print("⚠️ No bank data to save")
            return False
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        new_document = self.create_daily_document(bank_data_list)
        
        try:
            # Check if document for today already exists
            existing_doc = self.collection.find_one({'date': current_date})
            
            if existing_doc:
                print(f"📝 Found existing document for {current_date}. Updating...")
                
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
                        'data_completeness.banks_updated': list(new_banks.keys()),
                        'data_completeness.banks_count': len(merged_banks),
                        'data_completeness.update_timestamp': datetime.now()
                    }
                }
                
                result = self.collection.update_one({'date': current_date}, update_data)
                print(f"✅ Updated document for {current_date}")
                print(f"📊 Previous banks: {list(existing_banks.keys())}")
                print(f"🔄 Updated banks: {list(new_banks.keys())}")
                print(f"📈 Total banks now: {len(merged_banks)}")
                
            else:
                # Insert new document
                result = self.collection.insert_one(new_document)
                print(f"🆕 Created new document for {current_date}")
                print(f"📊 Banks added: {list(new_document['bank_rates'].keys())}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error saving to MongoDB Atlas: {e}")
            return False
    
    def get_daily_rates(self, date=None):
        """Get exchange rates for a specific date"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        return self.collection.find_one({'date': date})
    
    def close_connection(self):
        """Close MongoDB connection"""
        self.client.close()
        print("🔌 MongoDB connection closed")

def scrape_ntb_aud_rates():
    """
    Scrape AUD exchange rates directly from NTB (Nations Trust Bank) website
    Returns: Dictionary containing AUD buying and selling rates
    """
    
    url = "https://www.nationstrust.com/foreign-exchange-rates"
    
    # Headers to mimic a real browser request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        print("🌐 Scraping NTB directly from their website...")
        # Send GET request
        response = requests.get(url, headers=headers, timeout=10)
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
        
        # Debug: Check page content
        page_text = soup.get_text()
        if 'AUD' not in page_text:
            print("❌ AUD not found in NTB page content")
            return None
        
        # Method 1: Try to find AUD in tables
        tables = soup.find_all('table')
        print(f"🔍 Found {len(tables)} tables on NTB page")
        
        for table_idx, table in enumerate(tables):
            rows = table.find_all('tr')
            
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]
                
                # Look for AUD in the row
                if any('AUD' in cell for cell in row_text):
                    print(f"✅ Found AUD in NTB table {table_idx + 1}, row {row_idx + 1}: {row_text}")
                    
                    # Extract numeric values
                    numeric_values = []
                    for cell in row_text:
                        clean_cell = cell.replace(',', '').replace(' ', '')
                        numbers = re.findall(r'\d+\.\d+', clean_cell)
                        for num in numbers:
                            if float(num) > 50:
                                numeric_values.append(float(num))
                    
                    print(f"📊 Numeric values found: {numeric_values}")
                    
                    if len(numeric_values) >= 2:
                        # NTB typically shows: Currency, Demand Draft Buy, Demand Draft Sell, TT Buy, TT Sell, etc.
                        # We want the first two rates (Demand Draft rates)
                        aud_data['buying_rate'] = numeric_values[0]
                        aud_data['selling_rate'] = numeric_values[1]
                        print(f"✅ NTB Direct - Buying: {numeric_values[0]}, Selling: {numeric_values[1]}")
                        return aud_data
        
        # Method 2: If table parsing fails, try text parsing
        print("⚠️ Table parsing failed, trying text parsing...")
        lines = page_text.split('\n')
        for line in lines:
            if 'AUD' in line and any(char.isdigit() for char in line):
                print(f"🔍 Found AUD line: {line.strip()}")
                numbers = re.findall(r'\d+\.\d+', line.replace(',', ''))
                exchange_rates = [float(num) for num in numbers if float(num) > 50]
                
                if len(exchange_rates) >= 2:
                    aud_data['buying_rate'] = exchange_rates[0]
                    aud_data['selling_rate'] = exchange_rates[1]
                    print(f"✅ NTB Text parsing - Buying: {exchange_rates[0]}, Selling: {exchange_rates[1]}")
                    return aud_data
        
        print("❌ No AUD rates found with either method")
        return None
        
    except requests.RequestException as e:
        print(f"❌ Error fetching NTB webpage: {e}")
        return None
    except Exception as e:
        print(f"❌ Error parsing NTB data: {e}")
        import traceback
        traceback.print_exc()
        return None

def scrape_ntb_with_selenium():
    """
    Alternative NTB scraping method using Selenium WebDriver
    Use this if the site requires JavaScript rendering
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        print("🚀 Trying NTB with Selenium WebDriver...")
        
        # Chrome options
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # Run in background
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Use ChromeDriverManager for automatic driver management
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            print(f"⚠️ ChromeDriverManager failed: {e}")
            driver = webdriver.Chrome(options=chrome_options)
        
        try:
            print("🌐 Loading NTB page with Selenium...")
            driver.get("https://www.nationstrust.com/foreign-exchange-rates")
            
            # Wait for page to load and tables to appear
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            
            # Wait a bit more for dynamic content
            time.sleep(3)
            
            # Check page source for AUD
            page_source = driver.page_source
            if 'AUD' not in page_source:
                print("❌ AUD not found in Selenium page source")
                return None
            
            # Find all table rows
            rows = driver.find_elements(By.TAG_NAME, "tr")
            print(f"🔍 Selenium found {len(rows)} total rows")
            
            for row_idx, row in enumerate(rows):
                row_text = row.text.strip()
                if 'AUD' in row_text:
                    print(f"✅ Found AUD row {row_idx + 1}: {row_text}")
                    
                    # Extract rates
                    numbers = re.findall(r'\d+\.\d+', row_text.replace(',', ''))
                    exchange_rates = [float(num) for num in numbers if float(num) > 50]
                    
                    print(f"📊 Exchange rates found: {exchange_rates}")
                    
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
            
            print("❌ No AUD rates found with Selenium")
            return None
            
        finally:
            driver.quit()
            
    except ImportError:
        print("❌ Selenium not installed. Install with: pip install selenium webdriver-manager")
        return None
    except Exception as e:
        print(f"❌ Selenium scraping error for NTB: {e}")
        return None

def scrape_numbers_lk_aud_rates():
    """Scrape all AUD exchange rates from numbers.lk"""
    url = "https://tools.numbers.lk/exrates"
    
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        
        print("🚀 Setting up Selenium driver for numbers.lk...")
        
        # Chrome options for Docker environment
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Use ChromeDriverManager for automatic driver management
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            print(f"⚠️ ChromeDriverManager failed: {e}")
            driver = webdriver.Chrome(options=chrome_options)
        
        try:
            print("🌐 Loading numbers.lk exchange rates page...")
            driver.get(url)
            time.sleep(3)
            
            print("🔍 Looking for AUD currency option...")
            
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
                    print(f"✅ Found AUD element with selector: {selector}")
                    break
                except:
                    continue
            
            if aud_element:
                driver.execute_script("arguments[0].click();", aud_element)
                print("🖱️ Clicked on AUD currency")
                time.sleep(5)
            
            print("⏳ Waiting for AUD exchange rate data to load...")
            time.sleep(3)
            
            print("📊 Extracting bank exchange rate data...")
            bank_data = []
            
            # Try to find elements that contain bank names and rates
            all_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Bank') or contains(text(), 'HSBC')]")
            
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
                                        print(f"✅ Found: {normalized_bank_name} - Buy: {valid_rates[1]}, Sell: {valid_rates[0]}")
                                        break
                                
                except Exception as e:
                    continue
            
            # If we don't have enough banks, try comprehensive parsing
            if len(bank_data) < 8:
                print(f"⚠️ Only found {len(bank_data)} banks, trying comprehensive parsing...")
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
                                print(f"✅ Pattern match: {normalized_bank_name} - Buy: {rate2}, Sell: {rate1}")
                                break
            
            return bank_data
            
        finally:
            driver.quit()
            
    except ImportError:
        print("❌ Selenium not installed. Install with: pip install selenium webdriver-manager")
        return []
    except Exception as e:
        print(f"❌ Error scraping numbers.lk: {e}")
        return []

def enhance_with_direct_ntb_scraping(bank_data_list):
    """
    Enhance the bank data list with direct NTB scraping if NTB is missing or needs verification
    """
    # Check if NTB is already in the data
    ntb_found = False
    ntb_index = -1
    
    for idx, bank in enumerate(bank_data_list):
        if 'nations trust' in bank['bank'].lower() or 'ntb' in bank['bank'].lower():
            ntb_found = True
            ntb_index = idx
            break
    
    if ntb_found:
        print(f"📝 NTB already found in numbers.lk data: {bank_data_list[ntb_index]['bank']}")
        print(f"   Buy: {bank_data_list[ntb_index]['buying_rate']}, Sell: {bank_data_list[ntb_index]['selling_rate']}")
        print("🔄 Attempting direct NTB scraping for verification...")
    else:
        print("❌ NTB not found in numbers.lk data. Attempting direct scraping...")
    
    # Try direct NTB scraping
    print("\n🏦 Scraping NTB directly...")
    ntb_direct_data = scrape_ntb_aud_rates()
    
    if not ntb_direct_data or ntb_direct_data['buying_rate'] is None:
        print("⚠️ Primary NTB method failed. Trying Selenium...")
        ntb_direct_data = scrape_ntb_with_selenium()
    
    if ntb_direct_data and ntb_direct_data['buying_rate'] is not None:
        print(f"✅ Direct NTB scraping successful!")
        print(f"   Buy: {ntb_direct_data['buying_rate']}, Sell: {ntb_direct_data['selling_rate']}")
        
        if ntb_found:
            # Compare rates and decide which to use
            existing_ntb = bank_data_list[ntb_index]
            print(f"\n📊 Comparing NTB rates:")
            print(f"   numbers.lk: Buy {existing_ntb['buying_rate']}, Sell {existing_ntb['selling_rate']}")
            print(f"   Direct:     Buy {ntb_direct_data['buying_rate']}, Sell {ntb_direct_data['selling_rate']}")
            
            # Use direct scraping data (more reliable)
            bank_data_list[ntb_index] = ntb_direct_data
            print("✅ Using direct NTB data (more reliable)")
        else:
            # Add NTB data to the list
            bank_data_list.append(ntb_direct_data)
            print("✅ Added direct NTB data to bank list")
    else:
        print("❌ All NTB scraping methods failed")
        if not ntb_found:
            print("⚠️ NTB will be missing from final data")
    
    return bank_data_list

def print_bank_rates(bank_data_list):
    """Print all bank rates in a formatted way (people's perspective)"""
    if not bank_data_list:
        print("❌ No bank data found")
        return
    
    print("\n" + "="*80)
    print("🏦 ALL BANKS - AUD EXCHANGE RATES (People's Perspective)")
    print("="*80)
    
    for bank_info in bank_data_list:
        spread = bank_info['selling_rate'] - bank_info['buying_rate']
        source_indicator = "🌐" if bank_info.get('source') == 'numbers.lk' else "🏦"
        print(f"{source_indicator} Bank: {bank_info['bank']} [{bank_info.get('source', 'numbers.lk')}]")
        print(f"💰 You Sell AUD For: LKR {bank_info['buying_rate']} (Bank Buying Rate)")
        print(f"💸 You Buy AUD For: LKR {bank_info['selling_rate']} (Bank Selling Rate)")
        print(f"📊 Rate Spread: LKR {spread:.4f}")
        print(f"🕒 Timestamp: {bank_info['timestamp']}")
        print("-" * 50)
    
    # Show best rates for people
    best_selling_bank = max(bank_data_list, key=lambda x: x['buying_rate'])
    best_buying_bank = min(bank_data_list, key=lambda x: x['selling_rate'])
    
    print(f"🎯 BEST FOR YOU:")
    print(f"✅ Best Rate to Sell AUD: LKR {best_selling_bank['buying_rate']} at {best_selling_bank['bank']}")
    print(f"✅ Best Rate to Buy AUD: LKR {best_buying_bank['selling_rate']} at {best_buying_bank['bank']}")
    print(f"📈 Total Banks: {len(bank_data_list)}")
    
    # Show data sources summary
    sources = {}
    for bank in bank_data_list:
        source = bank.get('source', 'numbers.lk')
        sources[source] = sources.get(source, 0) + 1
    
    print(f"📡 Data Sources: {dict(sources)}")
    print("="*80)

if __name__ == "__main__":
    print("🚀 Enhanced AUD Exchange Rate Scraper")
    print("📡 Primary: numbers.lk + Direct NTB scraping for verification/backup")
    print("🔗 Connecting to MongoDB Atlas...")
    
    try:
        db = ExchangeRateDB()
        
        # Step 1: Scrape from numbers.lk (primary source)
        print("\n📡 Step 1: Scraping from numbers.lk...")
        numbers_lk_data = scrape_numbers_lk_aud_rates()
        
        if numbers_lk_data:
            print(f"✅ numbers.lk returned {len(numbers_lk_data)} banks")
        else:
            print("❌ numbers.lk scraping failed")
            numbers_lk_data = []
        
        # Step 2: Enhance with direct NTB scraping
        print("\n🏦 Step 2: Enhancing with direct NTB scraping...")
        enhanced_bank_data = enhance_with_direct_ntb_scraping(numbers_lk_data)
        
        # Step 3: Display and save results
        if enhanced_bank_data:
            print_bank_rates(enhanced_bank_data)
            success = db.upsert_daily_rates(enhanced_bank_data)
            
            if success:
                print(f"\n🎉 [SUCCESS] Successfully saved {len(enhanced_bank_data)} banks to MongoDB Atlas")
                bank_names = [bank['bank'] for bank in enhanced_bank_data]
                print(f"🏦 Banks: {', '.join(bank_names)}")
                
                # Show today's complete data
                today_data = db.get_daily_rates()
                if today_data:
                    print(f"\n📊 Today's complete document contains {today_data['total_banks']} banks:")
                    print("📈 Market Statistics (People's Perspective):")
                    stats = today_data['market_statistics']
                    print(f"  🟢 Best Rate to Sell AUD: {stats['people_selling']['best_bank']} (LKR {stats['people_selling']['max']})")
                    print(f"  🔵 Best Rate to Buy AUD: {stats['people_buying']['best_bank']} (LKR {stats['people_buying']['min']})")
                    print(f"  📊 Average Bank Buying: LKR {stats['people_selling']['avg']:.4f}")
                    print(f"  📊 Average Bank Selling: LKR {stats['people_buying']['avg']:.4f}")
                    
                    # Show which banks came from which sources
                    direct_scraped = [bank for bank in enhanced_bank_data if bank.get('source') != 'numbers.lk']
                    if direct_scraped:
                        print(f"\n🏦 Direct Scraped Banks: {', '.join([bank['bank'] for bank in direct_scraped])}")
            else:
                print("\n❌ [ERROR] Failed to save data to MongoDB Atlas")
        else:
            print("\n❌ [ERROR] Failed to scrape any bank data")
            print("This might be due to:")
            print("1. Website structure changes")
            print("2. ChromeDriver issues")
            print("3. Network connectivity")
            print("4. JavaScript loading issues")
        
        db.close_connection()
        
    except Exception as e:
        print(f"❌ MongoDB Atlas connection error: {e}")
        print("Please check:")
        print("1. MONGODB_CONNECTION_STRING in environment variables")
        print("2. Internet connection")
        print("3. MongoDB Atlas cluster is running")
        print("4. Database user credentials are correct")