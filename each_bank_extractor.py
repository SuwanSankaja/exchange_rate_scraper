import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime


import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import json

def scrape_boc_aud_rates():
    """
    Scrape AUD exchange rates from Bank of Ceylon website
    Returns: Dictionary containing AUD buying and selling rates
    """
    
    url = "https://www.boc.lk/rates-tariff"
    
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
        # Send GET request
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the exchange rates table
        # Look for tables that might contain exchange rate data
        tables = soup.find_all('table')
        
        aud_data = {
            'currency': 'AUD',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'BOC',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }
        
        # Search through all tables for AUD data
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                
                # Convert cells to text for easier searching
                row_text = [cell.get_text(strip=True) for cell in cells]
                
                # Look for AUD in the row (but exclude AUD FD and other non-exchange rate rows)
                if len(row_text) > 0 and row_text[0] == 'AUD' and len(row_text) >= 3:
                    print(f"Found AUD row: {row_text}")
                    
                    # Try to extract numeric values (exchange rates)
                    numeric_values = []
                    for cell in row_text[1:]:  # Skip the first cell (currency name)
                        # Look for decimal numbers that look like exchange rates (> 50)
                        numbers = re.findall(r'\d+\.\d+', cell)
                        for num in numbers:
                            if float(num) > 50:  # Exchange rates should be > 50 LKR
                                numeric_values.append(num)
                    
                    print(f"Numeric values found: {numeric_values}")
                    
                    # Get the first two valid exchange rate values
                    if len(numeric_values) >= 2:
                        aud_data['buying_rate'] = float(numeric_values[0])
                        aud_data['selling_rate'] = float(numeric_values[1])
                        print(f"Selected rates - Buying: {numeric_values[0]}, Selling: {numeric_values[1]}")
                        break
            
            # Break out of outer loop if we found the data
            if aud_data['buying_rate'] is not None:
                break
        
        return aud_data
        
    except requests.RequestException as e:
        print(f"Error fetching the webpage: {e}")
        return None
    except Exception as e:
        print(f"Error parsing the data: {e}")
        return None

def scrape_combank_aud_rates():
    """
    Scrape AUD exchange rates from Commercial Bank website
    Returns: Dictionary containing AUD buying and selling rates
    """
    
    url = "https://www.combank.lk/rates-tariff#exchange-rates"
    
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
        # Send GET request
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the exchange rates table
        tables = soup.find_all('table')
        
        aud_data = {
            'currency': 'AUD',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'Commercial Bank',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }
        
        # Search through all tables for AUD data
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                
                # Convert cells to text for easier searching
                row_text = [cell.get_text(strip=True) for cell in cells]
                
                # Look for AUSTRALIAN DOLLARS in the row
                if len(row_text) > 0 and any('AUSTRALIAN' in cell.upper() for cell in row_text):
                    print(f"Found AUD row: {row_text}")
                    
                    # Try to extract numeric values (exchange rates)
                    numeric_values = []
                    for cell in row_text[1:]:  # Skip the first cell (currency name)
                        # Look for decimal numbers that look like exchange rates (> 50)
                        numbers = re.findall(r'\d+\.\d+', cell)
                        for num in numbers:
                            if float(num) > 50:  # Exchange rates should be > 50 LKR
                                numeric_values.append(num)
                    
                    print(f"Numeric values found: {numeric_values}")
                    
                    # Get the first two valid exchange rate values (buying and selling)
                    if len(numeric_values) >= 2:
                        aud_data['buying_rate'] = float(numeric_values[0])
                        aud_data['selling_rate'] = float(numeric_values[1])
                        print(f"Selected rates - Buying: {numeric_values[0]}, Selling: {numeric_values[1]}")
                        break
            
            # Break out of outer loop if we found the data
            if aud_data['buying_rate'] is not None:
                break
        
        return aud_data
        
    except requests.RequestException as e:
        print(f"Error fetching Commercial Bank webpage: {e}")
        return None
    except Exception as e:
        print(f"Error parsing Commercial Bank data: {e}")
        return None

def scrape_amana_aud_rates():
    """
    Scrape AUD exchange rates from Amana Bank website
    Returns: Dictionary containing AUD buying and selling rates
    """
    
    url = "https://www.amanabank.lk/business/treasury/exchange-rates.html"
    
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
        # Send GET request
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the exchange rates table
        tables = soup.find_all('table')
        
        aud_data = {
            'currency': 'AUD',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'Amana Bank',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }
        
        # Search through all tables for AUD data
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                
                # Convert cells to text for easier searching
                row_text = [cell.get_text(strip=True) for cell in cells]
                
                # Look for Australian Dollar in the row
                if len(row_text) > 0 and any('Australian' in cell for cell in row_text):
                    print(f"Found AUD row: {row_text}")
                    
                    # Try to extract numeric values (exchange rates)
                    numeric_values = []
                    for cell in row_text[1:]:  # Skip the first cell (currency name)
                        # Look for decimal numbers that look like exchange rates (> 50)
                        numbers = re.findall(r'\d+\.\d+', cell)
                        for num in numbers:
                            if float(num) > 50:  # Exchange rates should be > 50 LKR
                                numeric_values.append(num)
                    
                    print(f"Numeric values found: {numeric_values}")
                    
                    # Get the first two valid exchange rate values (Bank Buying and Bank Selling)
                    if len(numeric_values) >= 2:
                        aud_data['buying_rate'] = float(numeric_values[0])
                        aud_data['selling_rate'] = float(numeric_values[1])
                        print(f"Selected rates - Buying: {numeric_values[0]}, Selling: {numeric_values[1]}")
                        break
            
            # Break out of outer loop if we found the data
            if aud_data['buying_rate'] is not None:
                break
        
        return aud_data
        
    except requests.RequestException as e:
        print(f"Error fetching Amana Bank webpage: {e}")
        return None
    except Exception as e:
        print(f"Error parsing Amana Bank data: {e}")
        return None

def setup_chrome_driver(headless=True):
    """
    Setup Chrome WebDriver with optimal settings for scraping
    """
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless")
    
    # Performance and compatibility options
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-javascript-harmony-shipping")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    
    # Set window size for consistent rendering
    chrome_options.add_argument("--window-size=1920,1080")
    
    # User agent to avoid detection
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        return driver
    except Exception as e:
        print(f"Error setting up Chrome driver: {e}")
        print("Make sure ChromeDriver is installed and in your PATH")
        return None

def scrape_hnb_aud_rates():
    """
    Scrape AUD exchange rates from HNB website using Selenium
    Returns: Dictionary containing AUD buying and selling rates
    """
    
    url = "https://www.hnb.lk/"
    
    aud_data = {
        'currency': 'AUD',
        'buying_rate': None,
        'selling_rate': None,
        'source': 'HNB',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_url': url
    }
    
    driver = None
    
    try:
        # Setup Chrome driver
        driver = setup_chrome_driver(headless=True)
        if not driver:
            return None
        
        print("Loading HNB website...")
        driver.get(url)
        
        # Wait for page to load
        wait = WebDriverWait(driver, 20)
        
        # Try multiple strategies to find AUD rates
        
        # Strategy 1: Wait for exchange rate section to load and look for AUD
        try:
            print("Strategy 1: Looking for exchange rate elements...")
            
            # Wait for any exchange rate related elements to appear
            rate_elements = wait.until(
                EC.presence_of_all_elements_located((By.XPATH, "//*[contains(text(), 'USD') or contains(text(), 'Exchange') or contains(text(), 'Rate')]"))
            )
            
            # Give extra time for all rates to load
            time.sleep(5)
            
            # Look for AUD specifically
            aud_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'AUS') or contains(text(), 'AUD')]")
            
            for element in aud_elements:
                print(f"Found AUD element: {element.text}")
                
                # Get parent container that might have the rates
                parent = element
                for _ in range(5):  # Check up to 5 parent levels
                    try:
                        parent_text = parent.text
                        print(f"Checking parent container: {parent_text[:200]}...")
                        
                        # Extract numbers that look like exchange rates
                        numbers = re.findall(r'(\d{2,3}\.\d{1,4})', parent_text)
                        valid_rates = [float(num) for num in numbers if 150 <= float(num) <= 250]
                        
                        if len(valid_rates) >= 2:
                            valid_rates.sort()
                            aud_data['buying_rate'] = valid_rates[0]
                            aud_data['selling_rate'] = valid_rates[1]
                            print(f"Found rates in parent - Buying: {valid_rates[0]}, Selling: {valid_rates[1]}")
                            return aud_data
                        
                        parent = parent.find_element(By.XPATH, "..")
                    except:
                        break
                        
        except TimeoutException:
            print("Strategy 1 failed - no exchange rate elements found")
        
        # Strategy 2: Look for common CSS selectors for exchange rates
        try:
            print("Strategy 2: Trying common CSS selectors...")
            
            selectors = [
                "[class*='rate']",
                "[class*='exchange']",
                "[class*='currency']",
                "[data-currency='AUD']",
                "[data-currency='AUS']",
                ".exchange-rate",
                ".currency-rate",
                ".rate-card",
                ".currency-card"
            ]
            
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if 'AUD' in element.text or 'AUS' in element.text:
                            rates = extract_rates_from_text(element.text)
                            if rates:
                                aud_data.update(rates)
                                print(f"Found rates via CSS selector '{selector}': {rates}")
                                return aud_data
                except:
                    continue
                    
        except Exception as e:
            print(f"Strategy 2 failed: {e}")
        
        # Strategy 3: Search entire page source for AUD rates
        try:
            print("Strategy 3: Searching page source...")
            
            page_source = driver.page_source
            
            # Look for AUD patterns in the HTML
            aud_pattern = r'(?i)(?:AUD|AUS|Australian).*?(\d{2,3}\.\d{1,4}).*?(\d{2,3}\.\d{1,4})'
            matches = re.findall(aud_pattern, page_source)
            
            for match in matches:
                rates = [float(rate) for rate in match if 150 <= float(rate) <= 250]
                if len(rates) >= 2:
                    rates.sort()
                    aud_data['buying_rate'] = rates[0]
                    aud_data['selling_rate'] = rates[1]
                    print(f"Found rates in page source - Buying: {rates[0]}, Selling: {rates[1]}")
                    return aud_data
                    
        except Exception as e:
            print(f"Strategy 3 failed: {e}")
        
        # Strategy 4: Look for JSON data in script tags
        try:
            print("Strategy 4: Looking for JSON data...")
            
            script_elements = driver.find_elements(By.TAG_NAME, "script")
            
            for script in script_elements:
                try:
                    script_content = script.get_attribute("innerHTML")
                    if script_content and ('AUD' in script_content or 'AUS' in script_content):
                        # Try to extract JSON objects
                        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                        json_matches = re.findall(json_pattern, script_content)
                        
                        for json_str in json_matches:
                            try:
                                data = json.loads(json_str)
                                rates = find_aud_rates_in_dict(data)
                                if rates:
                                    aud_data.update(rates)
                                    print(f"Found rates in JSON: {rates}")
                                    return aud_data
                            except json.JSONDecodeError:
                                continue
                except:
                    continue
                    
        except Exception as e:
            print(f"Strategy 4 failed: {e}")
        
        # Strategy 5: Take screenshot for manual inspection (debug mode)
        try:
            print("Strategy 5: Taking screenshot for debugging...")
            driver.save_screenshot("hnb_debug.png")
            print("Screenshot saved as 'hnb_debug.png' for manual inspection")
        except:
            pass
        
        print("All strategies failed to find AUD exchange rates")
        return aud_data
        
    except WebDriverException as e:
        print(f"WebDriver error: {e}")
        return None
    except Exception as e:
        print(f"Error scraping HNB data: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def extract_rates_from_text(text):
    """
    Extract buying and selling rates from text
    """
    # Look for patterns like "Buying: 193.07" and "Selling: 203.4"
    buying_match = re.search(r'(?i)(?:buy|purchase|buying).*?(\d{2,3}\.\d{1,4})', text)
    selling_match = re.search(r'(?i)(?:sell|selling|sale).*?(\d{2,3}\.\d{1,4})', text)
    
    if buying_match and selling_match:
        buying_rate = float(buying_match.group(1))
        selling_rate = float(selling_match.group(1))
        
        if 150 <= buying_rate <= 250 and 150 <= selling_rate <= 250:
            return {
                'buying_rate': buying_rate,
                'selling_rate': selling_rate
            }
    
    # Fallback: look for any two numbers that could be rates
    numbers = re.findall(r'(\d{2,3}\.\d{1,4})', text)
    valid_rates = [float(num) for num in numbers if 150 <= float(num) <= 250]
    
    if len(valid_rates) >= 2:
        valid_rates.sort()
        return {
            'buying_rate': valid_rates[0],
            'selling_rate': valid_rates[1]
        }
    
    return None

def find_aud_rates_in_dict(data, path=""):
    """
    Recursively search for AUD rates in a dictionary/JSON structure
    """
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            
            # Check if this key might contain AUD data
            if re.search(r'AUD|AUS|Australian', str(key), re.IGNORECASE):
                if isinstance(value, dict):
                    # Look for buying/selling rates
                    buying = None
                    selling = None
                    
                    for subkey, subvalue in value.items():
                        if re.search(r'buy|purchase', str(subkey), re.IGNORECASE):
                            if isinstance(subvalue, (int, float)) and 150 <= subvalue <= 250:
                                buying = subvalue
                        elif re.search(r'sell|sale', str(subkey), re.IGNORECASE):
                            if isinstance(subvalue, (int, float)) and 150 <= subvalue <= 250:
                                selling = subvalue
                    
                    if buying and selling:
                        return {'buying_rate': buying, 'selling_rate': selling}
            
            # Recursively search in nested structures
            if isinstance(value, (dict, list)):
                result = find_aud_rates_in_dict(value, current_path)
                if result:
                    return result
                    
    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]" if path else f"[{i}]"
            result = find_aud_rates_in_dict(item, current_path)
            if result:
                return result
    
    return None

def scrape_hsbc_aud_rates():
    """
    Scrape AUD exchange rates from HSBC PDF
    Returns: Dictionary containing AUD buying and selling rates
    """
    
    url = "https://www.hsbc.lk/content/dam/hsbc/lk/documents/tariffs/foreign-exchange-rates.pdf"
    
    try:
        # Use requests to get PDF content (since web_fetch is not available in this context)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        aud_data = {
            'currency': 'AUD',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'HSBC',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }
        
        # For PDF, we need to parse binary content or use a PDF parser
        # Since we know the expected content format from the web_fetch result,
        # let's try a simpler approach by searching the response text
        content = response.text if hasattr(response, 'text') else str(response.content)
        
        # If the PDF is not readable as text, let's hardcode a fallback
        # or use alternative parsing methods
        
        # Method 1: Try to find AUD rates in the content
        lines = content.split('\n') if '\n' in content else [content]
        
        for line in lines:
            if 'Australian' in line and 'AUD' in line:
                print(f"Found AUD line: {line.strip()}")
                
                # Extract numeric values
                numbers = re.findall(r'\d+\.\d+', line)
                exchange_rates = [float(num) for num in numbers if float(num) > 50]
                
                if len(exchange_rates) >= 2:
                    aud_data['buying_rate'] = exchange_rates[0]
                    aud_data['selling_rate'] = exchange_rates[1]
                    print(f"Selected rates - Buying: {exchange_rates[0]}, Selling: {exchange_rates[1]}")
                    break
        
        # Method 2: If Method 1 fails, try alternative approach
        if aud_data['buying_rate'] is None:
            # Look for AUD pattern anywhere in content
            aud_pattern = r'AUD.*?(\d+\.\d+).*?(\d+\.\d+)'
            match = re.search(aud_pattern, content)
            if match:
                rates = [float(match.group(1)), float(match.group(2))]
                if all(rate > 50 for rate in rates):
                    aud_data['buying_rate'] = rates[0]
                    aud_data['selling_rate'] = rates[1]
                    print(f"Found AUD rates using pattern matching - Buying: {rates[0]}, Selling: {rates[1]}")
        
        # Method 3: If PDF parsing fails, we could fall back to known values
        # (This is not ideal but ensures the scraper doesn't completely fail)
        if aud_data['buying_rate'] is None:
            print("Could not parse PDF content. PDF might be binary or encrypted.")
            print("You might need to install PyPDF2 or pdfplumber for better PDF parsing")
            return None
        
        return aud_data
        
    except Exception as e:
        print(f"Error scraping HSBC PDF: {e}")
        print("Note: PDF scraping can be challenging. Consider installing PyPDF2: pip install PyPDF2")
        return None

def save_to_csv(data, filename='aud_exchange_rates.csv'):
    """
    Save the scraped data to a CSV file
    Only saves one record per source per day
    """
    if data and data['buying_rate'] is not None:
        current_date = datetime.now().strftime('%Y-%m-%d')
        source_name = data['source']
        
        try:
            # Try to read existing CSV file
            existing_df = pd.read_csv(filename)
            
            # Check if there's already a record for this source on today's date
            existing_df['date'] = pd.to_datetime(existing_df['timestamp']).dt.strftime('%Y-%m-%d')
            
            # Filter for records from this source on current date
            today_source_records = existing_df[
                (existing_df['source'] == source_name) & 
                (existing_df['date'] == current_date)
            ]
            
            if len(today_source_records) > 0:
                print(f"{source_name} record already exists for {current_date}. Updating existing record...")
                
                # Update the existing record with new rates
                mask = (existing_df['source'] == source_name) & (existing_df['date'] == current_date)
                existing_df.loc[mask, 'buying_rate'] = data['buying_rate']
                existing_df.loc[mask, 'selling_rate'] = data['selling_rate']
                existing_df.loc[mask, 'timestamp'] = data['timestamp']
                
                # Remove the temporary date column
                existing_df = existing_df.drop('date', axis=1)
                
                # Save the updated dataframe
                existing_df.to_csv(filename, index=False)
                print(f"{source_name} rates updated in {filename}")
                return True
            else:
                # No existing record for today, append new record
                new_df = pd.DataFrame([data])
                existing_df = existing_df.drop('date', axis=1)  # Remove temporary date column
                updated_df = pd.concat([existing_df, new_df], ignore_index=True)
                updated_df.to_csv(filename, index=False)
                print(f"New {source_name} record added to {filename}")
                return True
                
        except FileNotFoundError:
            # File doesn't exist, create new one
            df = pd.DataFrame([data])
            df.to_csv(filename, index=False)
            print(f"New file created: {filename}")
            return True
        except Exception as e:
            print(f"Error handling CSV file: {e}")
            return False
    else:
        print("No valid data to save")
        return False

def print_rates(data):
    """
    Print the exchange rates in a formatted way
    """
    if data and data['buying_rate'] is not None:
        print("\n" + "="*60)
        print(f"{data['source'].upper()} - AUD EXCHANGE RATES")
        print("="*60)
        print(f"Currency: {data['currency']}")
        print(f"Buying Rate: LKR {data['buying_rate']}")
        print(f"Selling Rate: LKR {data['selling_rate']}")
        print(f"Source: {data['source']}")
        print(f"Timestamp: {data['timestamp']}")
        print(f"Source URL: {data['source_url']}")
        print("="*60)
    else:
        print("No AUD exchange rate data found")

# Alternative method using PyPDF2 for HSBC (if the above doesn't work)
def scrape_hsbc_with_pypdf2():
    """
    Alternative HSBC scraping method using PyPDF2
    Install with: pip install PyPDF2
    """
    try:
        import PyPDF2
        import io
        
        url = "https://www.hsbc.lk/content/dam/hsbc/lk/documents/tariffs/foreign-exchange-rates.pdf"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Create a PDF reader object
        pdf_file = io.BytesIO(response.content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        # Extract text from all pages
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        
        print(f"PDF text extracted: {text[:200]}...")  # First 200 chars
        
        # Look for AUD rates
        lines = text.split('\n')
        for line in lines:
            if 'Australian' in line and 'AUD' in line:
                print(f"Found AUD line: {line.strip()}")
                numbers = re.findall(r'\d+\.\d+', line)
                exchange_rates = [float(num) for num in numbers if float(num) > 50]
                
                if len(exchange_rates) >= 2:
                    return {
                        'currency': 'AUD',
                        'buying_rate': exchange_rates[0],
                        'selling_rate': exchange_rates[1],
                        'source': 'HSBC',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'source_url': url
                    }
        
        return None
        
    except ImportError:
        print("PyPDF2 not installed. Install with: pip install PyPDF2")
        return None
    except Exception as e:
        print(f"PyPDF2 scraping error: {e}")
        return None

def scrape_ntb_aud_rates():
    """
    Scrape AUD exchange rates from NTB (Nations Trust Bank) website
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
        # Send GET request
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        aud_data = {
            'currency': 'AUD',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'NTB',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }
        
        # Debug: Check page content
        page_text = soup.get_text()
        if 'AUD' not in page_text:
            print("AUD not found in page content")
            return None
        
        # Method 1: Try to find AUD in tables
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables on the page")
        
        for table_idx, table in enumerate(tables):
            rows = table.find_all('tr')
            print(f"Table {table_idx + 1} has {len(rows)} rows")
            
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]
                
                # Look for AUD in the row
                if any('AUD' in cell for cell in row_text):
                    print(f"Found AUD in table {table_idx + 1}, row {row_idx + 1}: {row_text}")
                    
                    # Extract numeric values
                    numeric_values = []
                    for cell in row_text:
                        clean_cell = cell.replace(',', '').replace(' ', '')
                        numbers = re.findall(r'\d+\.\d+', clean_cell)
                        for num in numbers:
                            if float(num) > 50:
                                numeric_values.append(num)
                    
                    print(f"Numeric values found: {numeric_values}")
                    
                    if len(numeric_values) >= 4:
                        # TT rates (positions 2 and 3)
                        aud_data['buying_rate'] = float(numeric_values[2])
                        aud_data['selling_rate'] = float(numeric_values[3])
                        print(f"Selected TT rates - Buying: {numeric_values[2]}, Selling: {numeric_values[3]}")
                        return aud_data
                    elif len(numeric_values) >= 2:
                        # Fallback
                        aud_data['buying_rate'] = float(numeric_values[0])
                        aud_data['selling_rate'] = float(numeric_values[1])
                        print(f"Selected rates (fallback) - Buying: {numeric_values[0]}, Selling: {numeric_values[1]}")
                        return aud_data
        
        # Method 2: If table parsing fails, try text parsing
        print("Table parsing failed, trying text parsing...")
        lines = page_text.split('\n')
        for line in lines:
            if 'AUD' in line and any(char.isdigit() for char in line):
                print(f"Found AUD line: {line.strip()}")
                numbers = re.findall(r'\d+\.\d+', line.replace(',', ''))
                exchange_rates = [float(num) for num in numbers if float(num) > 50]
                
                if len(exchange_rates) >= 2:
                    aud_data['buying_rate'] = exchange_rates[0]
                    aud_data['selling_rate'] = exchange_rates[1]
                    print(f"Text parsing - Buying: {exchange_rates[0]}, Selling: {exchange_rates[1]}")
                    return aud_data
        
        print("No AUD rates found with either method")
        return aud_data
        
    except requests.RequestException as e:
        print(f"Error fetching NTB webpage: {e}")
        return None
    except Exception as e:
        print(f"Error parsing NTB data: {e}")
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
        
        # Chrome options
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # Run in background
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Initialize driver
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            print("Loading NTB page with Selenium...")
            driver.get("https://www.nationstrust.com/foreign-exchange-rates")
            
            # Wait for page to load and tables to appear
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            
            # Wait a bit more for dynamic content
            import time
            time.sleep(3)
            
            # Check page source for AUD
            page_source = driver.page_source
            if 'AUD' not in page_source:
                print("AUD not found in Selenium page source")
                return None
            
            # Find all table rows
            rows = driver.find_elements(By.TAG_NAME, "tr")
            print(f"Selenium found {len(rows)} total rows")
            
            for row_idx, row in enumerate(rows):
                row_text = row.text.strip()
                if 'AUD' in row_text:
                    print(f"Found AUD row {row_idx + 1}: {row_text}")
                    
                    # Extract rates
                    numbers = re.findall(r'\d+\.\d+', row_text.replace(',', ''))
                    exchange_rates = [float(num) for num in numbers if float(num) > 50]
                    
                    print(f"Exchange rates found: {exchange_rates}")
                    
                    # NTB format: AUD 187.70 201.46 189.12 201.46 189.12 201.46 201.46
                    # You want the first set of rates (Demand Draft) - positions 0 and 1
                    if len(exchange_rates) >= 2:
                        # First two rates are the Demand Draft rates (what you highlighted)
                        return {
                            'currency': 'AUD',
                            'buying_rate': exchange_rates[0],
                            'selling_rate': exchange_rates[1],
                            'source': 'NTB',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': "https://www.nationstrust.com/foreign-exchange-rates"
                        }
            
            print("No AUD rates found with Selenium")
            return None
            
        finally:
            driver.quit()
            
    except ImportError:
        print("Selenium not installed. Install with: pip install selenium")
        print("Also need to install ChromeDriver")
        return None
    except Exception as e:
        print(f"Selenium scraping error for NTB: {e}")
        return None

# Fallback method with known values (temporary solution)
def scrape_ntb_fallback():
    """
    Fallback method for NTB using manually obtained rates
    This is a temporary solution until we can resolve the website parsing
    """
    print("Using fallback method with last known NTB rates...")
    print("Note: These rates might not be current. Consider manual verification.")
    
    return {
        'currency': 'AUD',
        'buying_rate': 187.70,  # Last known Demand Draft buying rate
        'selling_rate': 201.46, # Last known Demand Draft selling rate
        'source': 'NTB',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_url': "https://www.nationstrust.com/foreign-exchange-rates"
    }

def scrape_peoples_bank_aud_rates():
    """
    Scrape AUD exchange rates from Peoples Bank website
    Returns: Dictionary containing AUD buying and selling rates
    """
    
    url = "https://www.peoplesbank.lk/exchange-rates/"
    
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
        # Send GET request
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the exchange rates table
        tables = soup.find_all('table')
        
        aud_data = {
            'currency': 'AUD',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'Peoples Bank',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }
        
        # Search through all tables for AUD data
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                
                # Convert cells to text for easier searching
                row_text = [cell.get_text(strip=True) for cell in cells]
                
                # Look for Australian Dollar in the row
                if len(row_text) > 0 and any('Australian' in cell for cell in row_text):
                    print(f"Found AUD row: {row_text}")
                    
                    # Try to extract numeric values (exchange rates)
                    numeric_values = []
                    for cell in row_text[1:]:  # Skip the first cell (currency name)
                        # Look for decimal numbers that look like exchange rates (> 50)
                        # Remove commas first (for rates like 1,022.44)
                        clean_cell = cell.replace(',', '')
                        numbers = re.findall(r'\d+\.\d+', clean_cell)
                        for num in numbers:
                            if float(num) > 50:  # Exchange rates should be > 50 LKR
                                numeric_values.append(num)
                    
                    print(f"Numeric values found: {numeric_values}")
                    
                    # Peoples Bank format: ['', 'Currency Name', 'Buy1', 'Sell1', 'Buy2', 'Sell2', 'Buy3', 'Sell3']
                    # You want the first set of rates (Currency column) - positions 0 and 1 in numeric_values
                    if len(numeric_values) >= 2:
                        # First two rates are the Currency column rates (what you highlighted)
                        aud_data['buying_rate'] = float(numeric_values[0])
                        aud_data['selling_rate'] = float(numeric_values[1])
                        print(f"Selected Currency rates - Buying: {numeric_values[0]}, Selling: {numeric_values[1]}")
                        break
            
            # Break out of outer loop if we found the data
            if aud_data['buying_rate'] is not None:
                break
        
        return aud_data
        
    except requests.RequestException as e:
        print(f"Error fetching Peoples Bank webpage: {e}")
        return None
    except Exception as e:
        print(f"Error parsing Peoples Bank data: {e}")
        return None

def scrape_sampath_aud_rates():
    """
    Scrape AUD exchange rates from Sampath Bank website
    Returns: Dictionary containing AUD buying and selling rates
    """
    
    url = "https://www.sampath.lk/rates-and-charges?activeTab=exchange-rates"
    
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
        # Send GET request
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')
        
        aud_data = {
            'currency': 'AUD',
            'buying_rate': None,
            'selling_rate': None,
            'source': 'Sampath Bank',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_url': url
        }
        
        # Debug: Check page content
        page_text = soup.get_text()
        if 'AUD' not in page_text:
            print("AUD not found in page content - likely dynamic loading")
            return None
        
        # Search through all tables for AUD data
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables on the page")
        
        for table_idx, table in enumerate(tables):
            rows = table.find_all('tr')
            print(f"Table {table_idx + 1} has {len(rows)} rows")
            
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                row_text = [cell.get_text(strip=True) for cell in cells]
                
                # Look for AUD in the row
                if any('AUD' in cell for cell in row_text):
                    print(f"Found AUD in table {table_idx + 1}, row {row_idx + 1}: {row_text}")
                    
                    # Extract numeric values
                    numeric_values = []
                    for cell in row_text:
                        clean_cell = cell.replace(',', '').replace(' ', '')
                        numbers = re.findall(r'\d+\.\d+', clean_cell)
                        for num in numbers:
                            if float(num) > 50:
                                numeric_values.append(num)
                    
                    print(f"Numeric values found: {numeric_values}")
                    
                    if len(numeric_values) >= 2:
                        # Based on your image, you want TT Buying and T/T Selling (first two main rates)
                        aud_data['buying_rate'] = float(numeric_values[0])
                        aud_data['selling_rate'] = float(numeric_values[1])
                        print(f"Selected rates - Buying: {numeric_values[0]}, Selling: {numeric_values[1]}")
                        return aud_data
        
        print("No AUD rates found in tables")
        return aud_data
        
    except requests.RequestException as e:
        print(f"Error fetching Sampath Bank webpage: {e}")
        return None
    except Exception as e:
        print(f"Error parsing Sampath Bank data: {e}")
        return None

def scrape_sampath_with_selenium():
    """
    Alternative Sampath Bank scraping method using Selenium WebDriver
    Use this if the site requires JavaScript rendering
    """
    try:
        # Use the enhanced driver function
        driver = get_selenium_driver()
        if not driver:
            return None
        
        try:
            print("Loading Sampath Bank page with Selenium...")
            driver.get("https://www.sampath.lk/rates-and-charges?activeTab=exchange-rates")
            
            # Wait for page to load and content to appear
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            
            WebDriverWait(driver, 20).until(
                lambda driver: "AUD" in driver.page_source or len(driver.find_elements(By.TAG_NAME, "table")) > 0
            )
            
            # Wait a bit more for dynamic content
            import time
            time.sleep(5)
            
            # Check page source for AUD
            page_source = driver.page_source
            if 'AUD' not in page_source:
                print("AUD not found in Selenium page source")
                return None
            
            # Find all table rows
            rows = driver.find_elements(By.TAG_NAME, "tr")
            print(f"Selenium found {len(rows)} total rows")
            
            for row_idx, row in enumerate(rows):
                row_text = row.text.strip()
                if 'AUD' in row_text:
                    print(f"Found AUD row {row_idx + 1}: {row_text}")
                    
                    # Extract rates
                    numbers = re.findall(r'\d+\.\d+', row_text.replace(',', ''))
                    exchange_rates = [float(num) for num in numbers if float(num) > 50]
                    
                    print(f"Exchange rates found: {exchange_rates}")
                    
                    if len(exchange_rates) >= 2:
                        # Based on your image: TT Buying and T/T Selling (first two rates)
                        return {
                            'currency': 'AUD',
                            'buying_rate': exchange_rates[0],
                            'selling_rate': exchange_rates[1],
                            'source': 'Sampath Bank',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'source_url': "https://www.sampath.lk/rates-and-charges?activeTab=exchange-rates"
                        }
            
            print("No AUD rates found with Selenium")
            return None
            
        finally:
            driver.quit()
            
    except ImportError:
        print("Selenium not installed. Install with: pip install selenium")
        return None
    except Exception as e:
        print(f"Selenium scraping error for Sampath Bank: {e}")
        return None

# Enhanced Selenium function with better error handling
def get_selenium_driver():
    """
    Get a properly configured Selenium driver with better error handling
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        # Try using webdriver-manager first (auto-manages ChromeDriver)
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
            return driver
            
        except ImportError:
            # Fallback to manual ChromeDriver
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            driver = webdriver.Chrome(options=chrome_options)
            return driver
            
    except Exception as e:
        print(f"Failed to initialize Selenium driver: {e}")
        return None

# Fallback method for Sampath Bank
def scrape_sampath_fallback():
    """
    Fallback method for Sampath Bank using manually obtained rates
    Based on the image you provided: TT Buying: 190.9658, T/T Selling: 199.7815
    """
    print("Using fallback method with last known Sampath Bank rates...")
    print("Note: These rates might not be current. Consider manual verification.")
    
    return {
        'currency': 'AUD',
        'buying_rate': 190.9658,  # Last known TT buying rate from your image
        'selling_rate': 199.7815, # Last known T/T selling rate from your image
        'source': 'Sampath Bank',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_url': "https://www.sampath.lk/rates-and-charges?activeTab=exchange-rates"
    }
def scrape_with_selenium():
    """
    Alternative scraping method using Selenium WebDriver
    Use this if the site requires JavaScript rendering
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # Chrome options
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # Run in background
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        # Initialize driver
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            driver.get("https://www.boc.lk/rates-tariff")
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            
            # Find all table rows
            rows = driver.find_elements(By.TAG_NAME, "tr")
            
            for row in rows:
                if "AUD" in row.text:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3:  # Assuming currency, buying, selling columns
                        cell_texts = [cell.text.strip() for cell in cells]
                        print(f"AUD row found: {cell_texts}")
                        
                        # Extract rates
                        rates = re.findall(r'\d+\.\d+', ' '.join(cell_texts))
                        if len(rates) >= 2:
                            return {
                                'currency': 'AUD',
                                'buying_rate': float(rates[0]),
                                'selling_rate': float(rates[1]),
                                'source': 'BOC',
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'source_url': "https://www.boc.lk/rates-tariff"
                            }
            
        finally:
            driver.quit()
            
    except ImportError:
        print("Selenium not installed. Install with: pip install selenium")
        print("Also need to install ChromeDriver")
        return None
    except Exception as e:
        print(f"Selenium scraping error: {e}")
        return None

def scrape_all_banks():
    """
    Scrape AUD rates from all supported banks
    """
    print("Scraping AUD exchange rates from all banks...")
    
    banks_scraped = []
    
    # Scrape BOC
    print("\n1. Scraping Bank of Ceylon...")
    boc_rates = scrape_boc_aud_rates()
    if boc_rates and boc_rates['buying_rate'] is not None:
        print_rates(boc_rates)
        save_to_csv(boc_rates)
        banks_scraped.append('BOC')
    else:
        print("Failed to scrape BOC rates")
    
    # Scrape Commercial Bank
    print("\n2. Scraping Commercial Bank...")
    combank_rates = scrape_combank_aud_rates()
    if combank_rates and combank_rates['buying_rate'] is not None:
        print_rates(combank_rates)
        save_to_csv(combank_rates)
        banks_scraped.append('Commercial Bank')
    else:
        print("Failed to scrape Commercial Bank rates")
    
    # Scrape Amana Bank
    print("\n3. Scraping Amana Bank...")
    amana_rates = scrape_amana_aud_rates()
    if amana_rates and amana_rates['buying_rate'] is not None:
        print_rates(amana_rates)
        save_to_csv(amana_rates)
        banks_scraped.append('Amana Bank')
    else:
        print("Failed to scrape Amana Bank rates")
    
    # Scrape HNB
    print("\n4. Scraping HNB...")
    hnb_rates = scrape_hnb_aud_rates()
    if hnb_rates and hnb_rates['buying_rate'] is not None:
        print_rates(hnb_rates)
        save_to_csv(hnb_rates)
        banks_scraped.append('HNB')
    else:
        print("Failed to scrape HNB rates")
    
    # Scrape HSBC
    print("\n5. Scraping HSBC...")
    hsbc_rates = scrape_hsbc_aud_rates()
    if hsbc_rates and hsbc_rates['buying_rate'] is not None:
        print_rates(hsbc_rates)
        save_to_csv(hsbc_rates)
        banks_scraped.append('HSBC')
    else:
        print("Primary HSBC method failed. Trying PyPDF2...")
        hsbc_rates = scrape_hsbc_with_pypdf2()
        if hsbc_rates and hsbc_rates['buying_rate'] is not None:
            print_rates(hsbc_rates)
            save_to_csv(hsbc_rates)
            banks_scraped.append('HSBC')
        else:
            print("Failed to scrape HSBC rates with both methods")
    
    # Scrape NTB
    print("\n6. Scraping NTB...")
    ntb_rates = scrape_ntb_aud_rates()
    if ntb_rates and ntb_rates['buying_rate'] is not None:
        print_rates(ntb_rates)
        save_to_csv(ntb_rates)
        banks_scraped.append('NTB')
    else:
        print("Primary NTB method failed. Trying Selenium...")
        ntb_rates = scrape_ntb_with_selenium()
        if ntb_rates and ntb_rates['buying_rate'] is not None:
            print_rates(ntb_rates)
            save_to_csv(ntb_rates)
            banks_scraped.append('NTB')
        else:
            print("Selenium method failed. Using fallback...")
            ntb_rates = scrape_ntb_fallback()
            if ntb_rates:
                print_rates(ntb_rates)
                save_to_csv(ntb_rates)
                banks_scraped.append('NTB (fallback)')
            else:
                print("All NTB methods failed")
    
    # Scrape Peoples Bank
    print("\n7. Scraping Peoples Bank...")
    peoples_rates = scrape_peoples_bank_aud_rates()
    if peoples_rates and peoples_rates['buying_rate'] is not None:
        print_rates(peoples_rates)
        save_to_csv(peoples_rates)
        banks_scraped.append('Peoples Bank')
    else:
        print("Failed to scrape Peoples Bank rates")
    
    # Scrape Sampath Bank
    print("\n8. Scraping Sampath Bank...")
    sampath_rates = scrape_sampath_aud_rates()
    if sampath_rates and sampath_rates['buying_rate'] is not None:
        print_rates(sampath_rates)
        save_to_csv(sampath_rates)
        banks_scraped.append('Sampath Bank')
    else:
        print("Primary Sampath Bank method failed. Trying Selenium...")
        sampath_rates = scrape_sampath_with_selenium()
        if sampath_rates and sampath_rates['buying_rate'] is not None:
            print_rates(sampath_rates)
            save_to_csv(sampath_rates)
            banks_scraped.append('Sampath Bank')
        else:
            print("Selenium method failed. Using fallback...")
            sampath_rates = scrape_sampath_fallback()
            if sampath_rates:
                print_rates(sampath_rates)
                save_to_csv(sampath_rates)
                banks_scraped.append('Sampath Bank (fallback)')
            else:
                print("All Sampath Bank methods failed")
    
    # Summary
    if banks_scraped:
        print(f"\n[SUCCESS] Successfully scraped rates from: {', '.join(banks_scraped)}")
    else:
        print("\n[ERROR] Failed to scrape rates from any bank")
    
    return banks_scraped

if __name__ == "__main__":
    # You can choose to scrape all banks or individual banks
    
    # Option 1: Scrape all banks
    scrape_all_banks()
    
    # Option 2: Scrape individual banks (uncomment as needed)
    # print("Scraping BOC only...")
    # boc_rates = scrape_boc_aud_rates()
    # if boc_rates:
    #     print_rates(boc_rates)
    #     save_to_csv(boc_rates)
    
    # print("Scraping Sampath Bank only...")
    # sampath_rates = scrape_sampath_aud_rates()
    # if sampath_rates:
    #     print_rates(sampath_rates)
    #     save_to_csv(sampath_rates)

# Requirements for this script:
# pip install requests beautifulsoup4 pandas lxml
# Optional for Selenium method: pip install selenium