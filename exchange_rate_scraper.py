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
import sys

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
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=10000)
            self.db = self.client[db_name]
            self.collection = self.db.daily_rates
            
            # Create index on date for faster queries
            self.collection.create_index([("date", ASCENDING)], unique=True)
            
            # Test connection
            self.client.admin.command('ping')
            print(f"✅ Connected to MongoDB Atlas database: {db_name}")
            
        except ConnectionFailure as e:
            print(f"❌ Failed to connect to MongoDB Atlas: {e}")
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
                'last_updated': current_datetime
            }
            
            # Summary data for easy visualization
            bank_summary.append({
                'bank_name': bank_name,
                'buying_rate': bank_info['buying_rate'],
                'selling_rate': bank_info['selling_rate'],
                'spread': bank_info['selling_rate'] - bank_info['buying_rate']
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
            'source': 'numbers.lk',
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
                        'spread': bank_data['spread']
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

def scrape_numbers_lk_aud_rates():
    """Scrape all AUD exchange rates from numbers.lk - GitHub Actions optimized"""
    url = "https://tools.numbers.lk/exrates"
    
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        
        print("🚀 Setting up Chrome driver for GitHub Actions...")
        
        # Chrome options optimized for GitHub Actions
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--remote-debugging-port=9222')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')
        
        # Use system Chrome in GitHub Actions
        chrome_options.binary_location = '/usr/bin/google-chrome'
        
        try:
            # First try with webdriver-manager
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print("✅ Using ChromeDriverManager")
        except Exception as e:
            print(f"⚠️ ChromeDriverManager failed: {e}")
            # Fallback to system chromedriver
            try:
                driver = webdriver.Chrome(options=chrome_options)
                print("✅ Using system ChromeDriver")
            except Exception as e2:
                print(f"❌ Both ChromeDriver methods failed. Manager: {e}, System: {e2}")
                return []
        
        try:
            print("🌐 Loading numbers.lk exchange rates page...")
            driver.set_page_load_timeout(30)
            driver.get(url)
            time.sleep(5)
            
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
                time.sleep(8)
            
            print("⏳ Waiting for AUD exchange rate data to load...")
            time.sleep(5)
            
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
                                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'source_url': url
                                }
                                bank_data.append(bank_info)
                                print(f"✅ Pattern match: {normalized_bank_name} - Buy: {rate2}, Sell: {rate1}")
                                break
            
            return bank_data
            
        finally:
            driver.quit()
            print("🔌 Chrome driver closed")
            
    except ImportError:
        print("❌ Selenium not installed. Install with: pip install selenium")
        return []
    except Exception as e:
        print(f"❌ Error scraping numbers.lk: {e}")
        return []

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
        print(f"🏛️ Bank: {bank_info['bank']}")
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
    print("="*80)

if __name__ == "__main__":
    print("🚀 GitHub Actions - Scraping AUD exchange rates from all banks via numbers.lk...")
    print(f"⏰ Current time: {datetime.now()}")
    print("🔗 Connecting to MongoDB Atlas...")
    
    try:
        db = ExchangeRateDB()
        all_bank_data = scrape_numbers_lk_aud_rates()
        
        if all_bank_data:
            print_bank_rates(all_bank_data)
            success = db.upsert_daily_rates(all_bank_data)
            
            if success:
                print(f"\n🎉 [SUCCESS] Successfully saved {len(all_bank_data)} banks to MongoDB Atlas")
                bank_names = [bank['bank'] for bank in all_bank_data]
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
                
                # Exit with success
                sys.exit(0)
            else:
                print("\n❌ [ERROR] Failed to save data to MongoDB Atlas")
                sys.exit(1)
        else:
            print("\n❌ [ERROR] Failed to scrape any bank data")
            print("This might be due to:")
            print("1. Website structure changes")
            print("2. ChromeDriver issues")
            print("3. Network connectivity")
            print("4. JavaScript loading issues")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        try:
            db.close_connection()
        except:
            pass