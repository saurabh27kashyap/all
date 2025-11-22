"""
Universal Price Extractor - Extract prices from multiple e-commerce websites

This script supports two modes:
1. Simple Mode: Extract prices from a list of URLs (text file or simple CSV)
2. Product CSV Mode: Process product data CSV with multiple URL and price columns

Product CSV Mode Usage:
    python all.py data.csv [output.csv]
    
    The script automatically detects product CSV format if it contains:
    - style_id or product_title columns
    - URL columns ending with _url (e.g., myntra_url, slikk_url)
    - Price columns ending with _price (e.g., myntra_price, slikk_price)
    
    It will:
    - Go through each row
    - Check each URL-price pair
    - Fetch prices for missing/invalid entries
    - Update the CSV with new prices
    - Save to output file (default: updated.csv)

Supported Sites:
    Myntra, Ajio, Flipkart, Amazon, Slikk, Zilo, Bewakoof, 
    Sassafras, The Bear House, The Indian Garage Co, My Designation

Features:
    - Direct requests with user-agent rotation
    - Automatic retry logic (3 attempts)
    - Rate limiting (1 second between requests)
    - Comprehensive price extraction
    - No HTML files saved
"""

import csv
import requests
import re
from bs4 import BeautifulSoup
import time
import sys
import io
import random
from typing import Optional, Dict, List
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# -----------------------------
# CONFIG
# -----------------------------
OUTPUT_FILE = 'extracted_prices.csv'

# List of common user agents to rotate through
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
]

# -----------------------------
# PRICE EXTRACTOR CLASS
# -----------------------------

class PriceExtractor:
    """
    Extract prices from various e-commerce websites using direct requests.
    Supports multiple Indian and international e-commerce platforms.
    """
    
    def __init__(self, max_retries: int = 3, timeout: int = 30):
        """
        Initialize the Price Extractor.
        
        Args:
            max_retries: Maximum number of retry attempts per URL
            timeout: Request timeout in seconds
        """
        self.max_retries = max_retries
        self.timeout = timeout
        self.supported_sites = [
            'myntra', 'ajio', 'flipkart', 'amazon', 'tigc.in', 
            'slikk', 'zilo', 'bewakoof', 'sassafras', 'thebearhouse',
            'bearhouse', 'mydesignation'
        ]
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the list."""
        return random.choice(USER_AGENTS)
    
    def get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        if match:
            return match.group(1)
        return ''
    
    def extract_price_generic_regex(self, html_content: str) -> Optional[str]:
        """
        Try to extract price using generic regex patterns.
        Most reliable method that works across sites.
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Price string or None
        """
        price_patterns = [
            r'"price"[:\s]+["\']?(\d+)[\.\d]*["\']?',  # JSON price fields
            r'₹\s*(\d[\d,]*(?:\.\d{2})?)',  # Rupee symbol
            r'Rs\.?\s*(\d[\d,]*(?:\.\d{2})?)',  # Rs/Rs.
            r'INR\s*(\d[\d,]*(?:\.\d{2})?)',  # INR
            r'price["\s:]+(\d[\d,]+)',  # Generic price fields
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                # Get the first reasonable price (between 100 and 100000)
                for match in matches:
                    cleaned = re.sub(r'[,\s]', '', str(match))
                    try:
                        price_val = float(cleaned)
                        if 100 <= price_val <= 100000:  # Reasonable price range
                            return cleaned
                    except:
                        continue
        
        return None
    
    def extract_price_site_specific(self, soup: BeautifulSoup, domain: str) -> Optional[str]:
        """
        Extract price using site-specific selectors.
        
        Args:
            soup: BeautifulSoup object
            domain: Website domain
            
        Returns:
            Price string or None
        """
        price = None
        
        if 'myntra' in domain:
            # Myntra price selectors
            selectors = [
                {'class': 'pdp-price'},
                {'class': 'pdp-discount-container'},
                {'class': 'product-price'},
                {'class': 'price-value'}
            ]
            for selector in selectors:
                element = soup.find('span', selector)
                if element:
                    price = element.get_text()
                    break
            
            # Try JSON-LD structured data
            if not price:
                script = soup.find('script', type='application/ld+json')
                if script and script.string:
                    match = re.search(r'"price":\s*"?(\d+)"?', script.string)
                    if match:
                        price = match.group(1)
        
        elif 'ajio' in domain:
            # Ajio price selectors
            selectors = [
                {'class': 'prod-sp'},
                {'class': 'price'},
                {'class': 'price-value'}
            ]
            for selector in selectors:
                element = soup.find('span', selector)
                if element:
                    price = element.get_text()
                    break
        
        elif 'flipkart' in domain:
            # Flipkart price selectors
            selectors = [
                {'class': 'Nx9bqj'},
                {'class': '_30jeq3'},
                {'class': '_16Jk6d'}
            ]
            for selector in selectors:
                element = soup.find('div', selector)
                if element:
                    price = element.get_text()
                    break
        
        elif 'amazon' in domain:
            # Amazon price selectors
            selectors = [
                {'class': 'a-price-whole'},
                {'class': 'priceToPay'},
                {'id': 'priceblock_ourprice'},
                {'id': 'priceblock_dealprice'}
            ]
            for selector in selectors:
                if 'id' in selector:
                    element = soup.find('span', id=selector['id'])
                else:
                    element = soup.find('span', class_=selector.get('class'))
                if element:
                    price = element.get_text()
                    break
        
        elif 'tigc.in' in domain:
            # The Indian Garage Co price selectors
            selectors = [
                {'class': 'money'},
                {'class': 'price'},
                {'class': 'product-price'}
            ]
            for selector in selectors:
                element = soup.find('span', selector)
                if element:
                    price = element.get_text()
                    break
        
        elif 'slikk' in domain:
            # Slikk price selectors
            selectors = [
                {'class': 'font-semibold'},  # Primary price display
                {'class': 'price'},
                {'class': 'product-price'}
            ]
            for selector in selectors:
                element = soup.find('span', selector)
                if element:
                    text = element.get_text()
                    # Verify it contains a price
                    if '₹' in text or any(c.isdigit() for c in text):
                        price = text
                        break
        
        elif 'zilo' in domain:
            # Zilo price selectors
            selectors = [
                {'class': 'price'},
                {'class': 'product-price'}
            ]
            for selector in selectors:
                element = soup.find('span', selector)
                if element:
                    price = element.get_text()
                    break
        
        elif 'bewakoof' in domain:
            # Bewakoof price selectors
            selectors = [
                {'class': 'productPrice'},
                {'class': 'discountedPriceText'},
                {'class': 'sellingPrice'},
                {'class': 'price'},
                {'class': 'product-price'}
            ]
            for selector in selectors:
                # Try both span and div elements
                element = soup.find('span', selector) or soup.find('div', selector)
                if element:
                    text = element.get_text()
                    if '₹' in text or any(c.isdigit() for c in text):
                        price = text
                        break
        
        elif 'sassafras' in domain:
            # Sassafras price selectors (Shopify-based store)
            selectors = [
                {'class': 'money'},
                {'class': 'price-item--sale'},
                {'class': 'price-item--regular'},
                {'class': 'product-price'},
                {'class': 'price'}
            ]
            for selector in selectors:
                element = soup.find('span', selector) or soup.find('div', selector)
                if element:
                    text = element.get_text()
                    if '₹' in text or 'Rs' in text or any(c.isdigit() for c in text):
                        price = text
                        break
        
        elif 'thebearhouse' in domain or 'bearhouse' in domain:
            # The Bear House price selectors (Shopify-based store)
            selectors = [
                {'class': 'money'},
                {'class': 'price-item--sale'},
                {'class': 'price-item--regular'},
                {'class': 'product-price'},
                {'class': 'price'}
            ]
            for selector in selectors:
                element = soup.find('span', selector) or soup.find('div', selector)
                if element:
                    text = element.get_text()
                    if '₹' in text or 'Rs' in text or any(c.isdigit() for c in text):
                        price = text
                        break
        
        elif 'mydesignation' in domain:
            # My Designation price selectors
            selectors = [
                {'class': 'product-price'},
                {'class': 'price'},
                {'class': 'selling-price'},
                {'class': 'final-price'}
            ]
            for selector in selectors:
                element = soup.find('span', selector) or soup.find('div', selector)
                if element:
                    text = element.get_text()
                    if '₹' in text or 'Rs' in text or any(c.isdigit() for c in text):
                        price = text
                        break
        
        return price
    
    def extract_price_fallback(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Fallback method to find price in HTML when other methods fail.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Price string or None
        """
        # Try to find any element containing price-related text
        price_elements = soup.find_all(string=re.compile(r'[₹Rs][\s]?[\d,]+'))
        if price_elements:
            for elem in price_elements:
                match = re.search(r'[₹Rs][\s]?([\d,]+)', str(elem))
                if match:
                    return match.group(1)
        
        return None
    
    def clean_price(self, price: str) -> Optional[str]:
        """
        Clean and normalize price string to numeric format.
        
        Args:
            price: Raw price string
            
        Returns:
            Cleaned price string (numeric only) or None
        """
        if not price:
            return None
        
        # Remove currency symbols and text
        cleaned_price = re.sub(r'[₹Rs.,\s*INR]', '', str(price), flags=re.IGNORECASE)
        cleaned_price = re.sub(r'[^\d.]', '', cleaned_price)
        
        if cleaned_price and cleaned_price.replace('.', '').isdigit():
            # Remove decimal if it's .00
            if '.' in cleaned_price:
                cleaned_price = str(int(float(cleaned_price)))
            
            # Handle prices stored in paise (e.g., 99900 should be 999)
            # If price is > 10000 and divisible by 100, it might be in paise
            try:
                price_val = int(cleaned_price)
                if price_val > 10000 and price_val % 100 == 0:
                    # Check if dividing by 100 gives a reasonable price
                    possible_price = price_val // 100
                    if 100 <= possible_price <= 100000:
                        cleaned_price = str(possible_price)
            except:
                pass
            
            return cleaned_price
        
        return None
    
    def extract_price_from_html(self, html_content: str, url: str) -> Optional[str]:
        """
        Main price extraction method that tries multiple strategies.
        
        Args:
            html_content: HTML content of the page
            url: Source URL
            
        Returns:
            Extracted price or None
        """
        try:
            domain = self.get_domain(url)
            
            # Strategy 1: Try generic regex on raw HTML (most reliable)
            price = self.extract_price_generic_regex(html_content)
            if price:
                return self.clean_price(price)
            
            # Strategy 2: Try site-specific selectors
            soup = BeautifulSoup(html_content, 'html.parser')
            price = self.extract_price_site_specific(soup, domain)
            if price:
                return self.clean_price(price)
            
            # Strategy 3: Fallback - search for any price-like patterns
            price = self.extract_price_fallback(soup)
            if price:
                return self.clean_price(price)
            
            return None
        
        except Exception as e:
            print(f"  ⚠️ Error parsing HTML: {str(e)}")
            return None
    
    def fetch_url(self, url: str, verbose: bool = True) -> Optional[str]:
        """
        Fetch HTML content from a URL with retry logic.
        
        Args:
            url: The URL to fetch
            verbose: Whether to print detailed status messages
            
        Returns:
            HTML content as string, or None if all retries failed
        """
        if verbose:
            print(f"    🔍 Fetching: {url[:60]}...")
        
        for attempt in range(self.max_retries):
            user_agent = self._get_random_user_agent()
            headers = {'User-Agent': user_agent}
            
            try:
                response = requests.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()  # Raise exception for bad status codes
                
                if verbose:
                    print(f"    ✓ Success! Status code: {response.status_code}")
                return response.text
            
            except requests.exceptions.RequestException as e:
                if verbose:
                    print(f"    ✗ Attempt {attempt + 1}/{self.max_retries} failed: {type(e).__name__}")
                
                if attempt < self.max_retries - 1:
                    if verbose:
                        print(f"    Retrying with different user agent...")
                    time.sleep(1)  # Brief pause before retry
                else:
                    if verbose:
                        print(f"    All {self.max_retries} attempts failed")
        
        return None
    
    def scrape_price_from_url(self, url: str, verbose: bool = False) -> Optional[str]:
        """
        Fetch page and extract price.
        
        Args:
            url: URL to scrape
            verbose: Whether to print detailed messages
            
        Returns:
            Extracted price or None
        """
        if not url or url == 'Not Found':
            return None
        
        try:
            html_content = self.fetch_url(url, verbose=verbose)
            
            if html_content:
                price = self.extract_price_from_html(html_content, url)
                if price and verbose:
                    print(f"    ✅ Found price: ₹{price}")
                elif verbose:
                    print(f"    ⚠️ Price not found in page")
                return price
            else:
                return None
        
        except Exception as e:
            if verbose:
                print(f"    ❌ Error: {str(e)}")
            return None
    
    def get_price(self, url: str, verbose: bool = True) -> Dict[str, str]:
        """
        Get price from URL with status information.
        
        Args:
            url: URL to scrape
            verbose: Whether to print detailed messages
            
        Returns:
            Dictionary with url, price, and status
        """
        price = self.scrape_price_from_url(url, verbose=verbose)
        
        return {
            'url': url,
            'price': price if price else 'Not Found',
            'status': 'success' if price else 'failed'
        }
    
    def process_urls(self, urls: List[str], delay: float = 1) -> List[Dict[str, str]]:
        """
        Process multiple URLs and extract prices.
        
        Args:
            urls: List of URLs to process
            delay: Delay between requests in seconds
            
        Returns:
            List of results dictionaries
        """
        results = []
        
        print("="*80)
        print("🚀 PRICE EXTRACTOR - Direct Requests with User-Agent Rotation")
        print("="*80)
        print(f"📊 Total URLs to process: {len(urls)}")
        print()
        
        for idx, url in enumerate(urls, 1):
            print(f"🔄 [{idx}/{len(urls)}]")
            result = self.get_price(url)
            results.append(result)
            
            # Rate limiting - be nice to servers
            if idx < len(urls):
                time.sleep(delay)
            
            print()
        
        return results
    
    def save_to_csv(self, results: List[Dict[str, str]], output_file: str):
        """
        Save results to CSV file.
        
        Args:
            results: List of result dictionaries
            output_file: Output CSV filename
        """
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['URL', 'Price', 'Status'])
            
            for result in results:
                writer.writerow([result['url'], result['price'], result['status']])
        
        print("="*80)
        print(f"✅ Results saved to: {output_file}")
        print("="*80)
    
    def print_summary(self, results: List[Dict[str, str]]):
        """Print summary of extraction results."""
        total = len(results)
        successful = sum(1 for r in results if r['status'] == 'success')
        failed = total - successful
        
        print("\n" + "="*80)
        print("📊 SUMMARY")
        print("="*80)
        print(f"Total URLs processed: {total}")
        print(f"Prices found: {successful}")
        print(f"Prices not found: {failed}")
        print(f"Success rate: {(successful/total*100):.1f}%")
        print("="*80)

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

def load_urls_from_file(filepath: str = 'urls.txt') -> List[str]:
    """
    Load URLs from a text file.
    
    Args:
        filepath: Path to file containing URLs (one per line)
        
    Returns:
        List of URLs
    """
    urls = []
    invalid_keywords = ['not found', 'error', 'n/a', 'none', '404']
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Skip invalid entries
                if any(keyword in line.lower() for keyword in invalid_keywords):
                    print(f"Skipping invalid entry at line {line_num}: {line}")
                    continue
                
                # Validate URL
                if line.startswith('http://') or line.startswith('https://'):
                    urls.append(line)
                else:
                    print(f"Skipping non-URL entry at line {line_num}: {line}")
        
        print(f"\n📥 Loaded {len(urls)} valid URLs from {filepath}\n")
        return urls
    
    except FileNotFoundError:
        print(f"❌ Error: File '{filepath}' not found!")
        return []

def load_urls_from_csv(filepath: str, url_column: str = 'url') -> List[str]:
    """
    Load URLs from a CSV file.
    
    Args:
        filepath: Path to CSV file
        url_column: Name of column containing URLs
        
    Returns:
        List of URLs
    """
    urls = []
    
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            if url_column not in reader.fieldnames:
                print(f"❌ Error: Column '{url_column}' not found in CSV!")
                print(f"Available columns: {', '.join(reader.fieldnames)}")
                return []
            
            for row in reader:
                url = row.get(url_column, '').strip()
                if url and url.startswith('http'):
                    urls.append(url)
        
        print(f"\n📥 Loaded {len(urls)} URLs from {filepath}\n")
        return urls
    
    except FileNotFoundError:
        print(f"❌ Error: File '{filepath}' not found!")
        return []
    except Exception as e:
        print(f"❌ Error reading CSV: {str(e)}")
        return []


def should_update_price(price_value: str, force_update: bool = False) -> bool:
    """
    Check if we should update/fetch this price.
    
    Args:
        price_value: Current price value from CSV
        force_update: If True, update all prices regardless of current value
        
    Returns:
        True if price should be updated
    """
    if force_update:
        return True
    
    invalid_values = [
        'Check site for price',
        'Product not available on site',
        'Not Found',
        'N/A',
        '',
        'Error'
    ]
    return price_value in invalid_values or not price_value


def process_product_csv(input_file: str, output_file: str, extractor: PriceExtractor, force_update: bool = True):
    """
    Process a CSV file with product data and update prices.
    
    Args:
        input_file: Input CSV file path
        output_file: Output CSV file path
        extractor: PriceExtractor instance
        force_update: If True, fetch fresh prices for ALL URLs (default: True)
    """
    print("="*80)
    print("🛍️  PROCESSING PRODUCT CSV WITH PRICE UPDATES")
    print("="*80)
    print(f"📥 Input: {input_file}")
    print(f"📤 Output: {output_file}")
    if force_update:
        print(f"🔄 Mode: FORCE UPDATE - Fetching fresh prices for ALL URLs")
    else:
        print(f"🔄 Mode: SMART UPDATE - Only updating missing/invalid prices")
    print()
    
    # Read input CSV
    try:
        with open(input_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
    except FileNotFoundError:
        print(f"❌ Error: File '{input_file}' not found!")
        return
    except Exception as e:
        print(f"❌ Error reading CSV: {str(e)}")
        return
    
    print(f"📊 Total products to process: {len(rows)}")
    print()
    
    # Define URL-Price column pairs to check
    url_price_pairs = [
        ('myntra_url', 'myntra_price'),
        ('ajio_url', 'ajio_price'),
        ('flipkart_url', 'flipkart_price'),
        ('amazon_url', 'amazon_price'),
        ('zilo_url', 'zilo_price'),
        ('slikk_url', 'slikk_price'),
        ('bewakoof_url', 'bewakoof_price'),
        ('sassafras_url', 'sassafras_price'),
        ('indian_garage_co_url', 'indian_garage_co_price'),
        ('tigc_url', 'tigc_price'),
        ('bearhouse_url', 'bearhouse_price'),
        ('mydesignation_url', 'mydesignation_price')
    ]
    
    # Process each row
    for idx, row in enumerate(rows, 1):
        product_title = row.get('product_title', 'Unknown Product')[:50]
        style_id = row.get('style_id', 'N/A')
        
        print(f"🔄 [{idx}/{len(rows)}] {product_title}")
        print(f"   Style ID: {style_id}")
        
        prices_updated = 0
        
        # Check each URL-price pair
        for url_col, price_col in url_price_pairs:
            # Check if columns exist in this CSV
            if url_col not in row or price_col not in row:
                continue
            
            url = row.get(url_col, '').strip()
            current_price = row.get(price_col, '').strip()
            
            # Skip if no URL or URL is "Not Found"
            if not url or url == 'Not Found':
                continue
            
            # Check if we should update this price
            if should_update_price(current_price, force_update=force_update):
                site_name = url_col.replace('_url', '').replace('_', ' ').title()
                print(f"  🌐 {site_name}: Fetching...", end=' ')
                
                # Fetch the price (non-verbose for cleaner output)
                price = extractor.scrape_price_from_url(url, verbose=False)
                
                if price:
                    row[price_col] = price
                    prices_updated += 1
                    print(f"✅ ₹{price}")
                else:
                    # Keep existing value or set to "Not Found"
                    row[price_col] = 'Product not available on site'
                    print(f"⚠️ Not found")
                
                # Rate limiting - be nice to servers
                time.sleep(1)
        
        if prices_updated > 0:
            print(f"  ✨ Updated {prices_updated} price(s) for this product")
        else:
            print(f"  ℹ️  No prices needed updating")
        print()
    
    # Write output CSV
    try:
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print("="*80)
        print(f"✅ COMPLETE! Updated CSV saved to: {output_file}")
        print("="*80)
        
        # Print summary
        total_prices = 0
        updated_prices = 0
        for url_col, price_col in url_price_pairs:
            if price_col in fieldnames:
                for row in rows:
                    if row.get(price_col) and row.get(price_col) not in ['Not Found', 'Product not available on site', 'Check site for price', '', 'N/A']:
                        if row.get(price_col).replace('.', '').isdigit():
                            updated_prices += 1
                    if row.get(url_col) and row.get(url_col) != 'Not Found':
                        total_prices += 1
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total URLs found: {total_prices}")
        print(f"   Prices successfully extracted: {updated_prices}")
        print(f"   Success rate: {(updated_prices/total_prices*100):.1f}%" if total_prices > 0 else "   Success rate: 0%")
        
    except Exception as e:
        print(f"❌ Error writing output CSV: {str(e)}")

# -----------------------------
# MAIN FUNCTION
# -----------------------------

def main():
    """Main function to demonstrate usage."""
    import sys
    
    # ==============================================
    # INPUT/OUTPUT FILES - Change these as needed
    # ==============================================
    INPUT_CSV = 'bear.csv'
    OUTPUT_CSV = 'pb.csv'
    
    print("\n" + "="*80)
    print("🛍️  UNIVERSAL PRICE EXTRACTOR")
    print("="*80)
    print("Supports: Myntra, Ajio, Flipkart, Amazon, Slikk, Zilo,")
    print("          Bewakoof, Sassafras, The Bear House, My Designation, and more!")
    print("="*80 + "\n")
    
    # Create price extractor with retry logic
    extractor = PriceExtractor(
        max_retries=3,
        timeout=30
    )
    
    # Check command line arguments (command line overrides constants)
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_file_override = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        input_file = INPUT_CSV
        output_file_override = None
    
    # Check if this is a product CSV (has columns like myntra_url, myntra_price, etc.)
    if input_file.endswith('.csv'):
        try:
            # Peek at the CSV to check if it's a product data CSV
            with open(input_file, 'r', encoding='utf-8-sig', newline='') as f:
                # Read first line to get headers
                first_line = f.readline().strip()
                if not first_line:
                    print(f"❌ Error: Empty CSV file: {input_file}")
                    return
                
                fieldnames = [col.strip() for col in first_line.split(',')]
                
                # Check if it has product-specific columns
                has_style_id = 'style_id' in fieldnames
                has_product_title = 'product_title' in fieldnames
                has_url_columns = any(col.endswith('_url') for col in fieldnames)
                
                if (has_style_id or has_product_title) and has_url_columns:
                    # This is a product CSV - process it specially
                    print("📋 Detected product data CSV format")
                    output_file = output_file_override if output_file_override else OUTPUT_CSV
                    # Force update all prices - fetch fresh data from all URLs
                    process_product_csv(input_file, output_file, extractor, force_update=True)
                    return
                else:
                    # Regular CSV with just URLs
                    url_column = 'url'
                    if len(sys.argv) > 2 and not output_file_override:
                        url_column = sys.argv[2]
                    urls = load_urls_from_csv(input_file, url_column)
        except Exception as e:
            print(f"❌ Error reading CSV: {str(e)}")
            import traceback
            traceback.print_exc()
            return
    else:
        urls = load_urls_from_file(input_file)
    
    if not urls:
        print("❌ No valid URLs to process. Exiting.")
        print("\nUsage:")
        print("  python all.py urls.txt")
        print("  python all.py data.csv [updated.csv]")
        print("  python all.py simple_urls.csv url_column_name")
        return
    
    # Process URLs (simple mode)
    results = extractor.process_urls(urls, delay=1)
    
    # Save results
    extractor.save_to_csv(results, OUTPUT_FILE)
    
    # Print summary
    extractor.print_summary(results)

if __name__ == "__main__":
    main()

