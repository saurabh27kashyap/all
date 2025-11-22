import requests
import csv
import sys
import io
import time
import re
from urllib.parse import urlparse

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# === CONFIGURATION ===
API_KEY = "b9d487e6b2fb018ae6f316980030c95661567bc024528e9e7353a7f2e07f1611"

# Coverage threshold - trigger second pass if below this
COVERAGE_THRESHOLD = 0.50  # 50%

# Primary sites - Always search these
PRIMARY_SITES = ["myntra", "slikk"]

# Target shopping sites - Primary 2 + Brand sites
SHOPPING_SITES = {
    "myntra": ["myntra.com"],
    "slikk": ["slikk.club"],
    "bewakoof": ["bewakoof.com"],
    "sassafras": ["sassafras.in"],
    "indian_garage_co": ["tigc.in"],
    "bearhouse": ["thebearhouse.com", "bearhouseindia.com", "thebearhouse.in"],
    "bearcompany": ["bearcompany.in", "thebearcompany.com"],
    "mydesignation": ["mydesignation.com"]
}

def get_allowed_sites(brand_name):
    """
    Get list of sites to search based on brand
    Returns: Primary 2 sites (Myntra, Slikk) + Brand's own site (if applicable)
    """
    allowed = PRIMARY_SITES.copy()
    
    # Convert brand name to lowercase for matching
    brand_lower = brand_name.lower().replace(" ", "").replace("-", "").replace("_", "")
    
    # Enhanced brand mapping with more variations
    brand_mapping = {
        "bewakoof": "bewakoof",
        "sassafras": "sassafras",
        "indiangarageco": "indian_garage_co",
        "indiangaragecompany": "indian_garage_co",
        "theindiangaragecompany": "indian_garage_co",
        "theindiangaragecom": "indian_garage_co",
        "theindiangarageco": "indian_garage_co",
        "theindiangarage": "indian_garage_co",
        "bearhouse": "bearhouse",
        "thebearhouse": "bearhouse",
        "bearhouseindia": "bearhouse",
        "thebearhouseindia": "bearhouse",
        "bearcompany": "bearcompany",
        "thebearcompany": "bearcompany",
        "bear": "bearcompany",
        "bearco": "bearcompany",
        "mydesignation": "mydesignation",
        "designation": "mydesignation",
    }
    
    # Add brand's own site if it exists in our database
    brand_site = brand_mapping.get(brand_lower)
    if brand_site and brand_site in SHOPPING_SITES and brand_site not in allowed:
        allowed.append(brand_site)
    
    return allowed

def extract_domain(url):
    """Extract clean domain from URL"""
    try:
        parsed = urlparse(url.lower())
        domain = parsed.netloc.replace('www.', '')
        return domain
    except:
        return ""

def identify_site(url):
    """Identify which shopping site the URL belongs to"""
    domain = extract_domain(url)
    url_lower = url.lower()
    
    for site_key, site_patterns in SHOPPING_SITES.items():
        for pattern in site_patterns:
            if pattern in domain or pattern in url_lower:
                return site_key
    return None

def extract_price_from_match(match_data):
    """
    Extract price from match data - handles all possible price formats from SerpAPI
    Returns only numeric values without currency symbols
    """
    price_info = match_data.get("price", {})
    
    # Case 1: Price is a dictionary with 'value' and/or 'extracted_value'
    if isinstance(price_info, dict):
        # Try 'value' first (formatted string like "₹660*")
        price_value = price_info.get("value", "")
        if price_value and price_value not in ["N/A", "", "null"]:
            # Clean the price value
            cleaned = re.sub(r'[₹Rs.,\s*INR]', '', price_value, flags=re.IGNORECASE)
            if cleaned and cleaned.replace('.', '').isdigit():
                return cleaned
        
        # Try 'extracted_value' (usually numeric)
        extracted = price_info.get("extracted_value", "")
        if extracted and str(extracted) not in ["N/A", "", "null"]:
            return str(extracted)
    
    # Case 2: Price is a string
    elif isinstance(price_info, str):
        if price_info and price_info not in ["N/A", "", "null"]:
            cleaned = re.sub(r'[₹Rs.,\s*INR]', '', price_info, flags=re.IGNORECASE)
            if cleaned and cleaned.replace('.', '').isdigit():
                return cleaned
    
    return "Price not displayed in listing"

def extract_colors_from_title(title):
    """Extract color keywords from title"""
    colors = [
        'black', 'white', 'blue', 'red', 'green', 'yellow', 'pink', 'purple', 
        'orange', 'brown', 'grey', 'gray', 'beige', 'navy', 'olive', 'maroon',
        'silver', 'gold', 'cream', 'khaki', 'tan', 'teal', 'burgundy', 'mint',
        'lavender', 'coral', 'peach', 'mustard', 'charcoal', 'rose'
    ]
    
    title_lower = title.lower()
    found_colors = [c for c in colors if c in title_lower]
    return found_colors

def check_brand_relaxed_match(match, target_brand, site_key):
    """
    RELAXED brand verification with site-specific rules
    - Brand's own site: Accept all (site presence = brand verified)
    - Marketplaces: Require brand in title OR URL
    Returns True if brand match is acceptable
    """
    title = match.get("title", "").lower()
    link = match.get("link", "").lower()
    source = match.get("source", "").lower()
    
    # If product is on brand's own website, skip brand verification
    if site_key and site_key not in ['myntra', 'slikk']:
        return True
    
    # For marketplaces, check brand presence
    target_lower = target_brand.lower()
    
    # Generate brand variations to check
    brand_keywords = target_lower.replace("-", " ").replace("_", " ").split()
    
    brand_variations = [
        target_lower.replace(" ", ""),
        target_lower.replace(" ", "-"),
        target_lower.replace(" ", "_"),
        target_lower,
    ]
    
    if len(brand_keywords) > 1:
        combined = "".join(brand_keywords)
        brand_variations.append(combined)
        
        if brand_keywords[0] in ["the"]:
            without_the = " ".join(brand_keywords[1:])
            brand_variations.append(without_the)
            brand_variations.append(without_the.replace(" ", ""))
    
    # Special brand-specific variations
    if "bear" in target_lower:
        brand_variations.extend([
            "bear", "bearhouse", "bear house", "thebearhouse", "the bear house",
            "bearcompany", "bear company", "thebearcompany", "the bear company",
        ])
    
    if "bewakoof" in target_lower:
        brand_variations.extend(["bewakoof", "bwkf"])
    
    if "indian" in target_lower and "garage" in target_lower:
        brand_variations.extend(["indiangarage", "indian garage", "tigc"])
    
    # Check if ANY brand variation exists in title, link, or source
    combined_text = f"{title} {link} {source}"
    
    for variation in brand_variations:
        if variation and len(variation) > 2 and variation in combined_text:
            return True
    
    return False

def is_valid_product_url(url):
    """
    STRICT URL validation - reject category/collection/search pages
    Returns True for actual product pages only
    """
    url_lower = url.lower()
    
    # Invalid patterns - these indicate non-product pages
    invalid_patterns = [
        '/collections/', '/collection/', '/category/', '/categories/',
        '/search', '?search=', '/s?', '/find/',
        '/brand/', '/brands/', '/sale/', '/deals/',
        '/all-products', '/shop?',
        '/filter', '/sort=',
        '?page=', '&page=',  # Pagination
        '/men/', '/women/', '/kids/', '/unisex/',
        '/clothing/', '/accessories/', '/footwear/'
    ]
    
    # Check for invalid patterns
    for pattern in invalid_patterns:
        if pattern in url_lower:
            return False
    
    # BEWAKOOF - STRICT validation to avoid category pages
    if 'bewakoof.com' in url_lower:
        if '/p/' in url_lower:
            slug = url_lower.split('/p/')[-1].strip('/')
            
            # Detect CATEGORY pages (generic URLs)
            category_keywords = [
                'hoodies', 'tshirts', 'shirts', 'jeans', 'dresses', 'kurtas',
                'pants', 'shorts', 'jackets', 'sweaters', 'sweatshirts',
                'tops', 'bottoms', 'skirts', 'trousers'
            ]
            
            # Check for generic category patterns
            for keyword in category_keywords:
                # Pattern: mens-blue-hoodies-16 (ends with short number)
                pattern = f"{keyword}-\\d{{1,3}}$"
                if re.search(pattern, slug):
                    return False
            
            # Count descriptive words (product URLs have more detail)
            word_count = len(slug.split('-'))
            if word_count < 4:
                return False
            
            # Check product ID length (last segment)
            last_segment = slug.split('-')[-1]
            if last_segment.isdigit():
                if len(last_segment) < 5:  # Category IDs are short (16, 24, etc.)
                    return False
            else:
                # No numeric ID at end - require very specific (6+ words)
                if word_count < 6:
                    return False
            
            return True
        
        return '/product/' in url_lower or '/buy' in url_lower
    
    # MYNTRA validation
    elif 'myntra.com' in url_lower:
        return '/buy' in url_lower or '/p/' in url_lower
    
    # SLIKK validation
    elif 'slikk.club' in url_lower:
        if '/shop' in url_lower or '/product' in url_lower:
            parts = url_lower.split('/shop') if '/shop' in url_lower else url_lower.split('/product')
            if len(parts) > 1 and len(parts[1].strip('/')) > 1:
                return True
        return True
    
    # MYDESIGNATION validation
    elif 'mydesignation.com' in url_lower:
        return '/products/' in url_lower
    
    # SASSAFRAS validation
    elif 'sassafras.in' in url_lower:
        return '/products/' in url_lower
    
    # BEAR BRANDS validation
    elif 'bearhouse' in url_lower or 'bearcompany' in url_lower or 'thebearhouse' in url_lower:
        return '/products/' in url_lower or '/product/' in url_lower
    
    # TIGC validation
    elif 'tigc.in' in url_lower:
        return '/products/' in url_lower
    
    # Generic validation: Accept URLs with 3+ meaningful path segments
    path_segments = [s for s in url_lower.split('/') if s and not s.startswith('?')]
    return len(path_segments) >= 3

def search_image_on_serpapi(image_url):
    """
    Search for visually similar products using SerpAPI Google Lens
    PURE IMAGE SEARCH - No text query
    FRESH DATA - No cache
    """
    params = {
        "engine": "google_lens",
        "url": image_url,
        "api_key": API_KEY,
        "country": "in",
        "hl": "en",
        "no_cache": "true"
    }
    
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"  ❌ API Error: {str(e)}")
        return None

def search_image_with_query_on_serpapi(image_url, query_text):
    """
    Search with Image + Query
    FRESH DATA - No cache
    """
    params = {
        "engine": "google_lens",
        "url": image_url,
        "q": query_text,
        "api_key": API_KEY,
        "country": "in",
        "hl": "en",
        "no_cache": "true"
    }
    
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"  ❌ API Error: {str(e)}")
        return None

def calculate_title_similarity(original_title, found_title):
    """
    Calculate similarity between original and found product titles
    Returns a score between 0-100
    Includes color matching bonus/penalty
    """
    if not original_title or not found_title:
        return 0
    
    # Normalize titles
    orig_lower = original_title.lower()
    found_lower = found_title.lower()
    
    # Extract keywords (ignore common words)
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'with', 'for', 'on', 'in', 'at', 'to', 'buy', 'shop', 'online'}
    
    orig_keywords = set(re.findall(r'\b\w+\b', orig_lower)) - stop_words
    found_keywords = set(re.findall(r'\b\w+\b', found_lower)) - stop_words
    
    if not orig_keywords:
        return 0
    
    # Calculate keyword overlap
    common_keywords = orig_keywords & found_keywords
    overlap_score = (len(common_keywords) / len(orig_keywords)) * 100
    
    # Extract and compare colors
    orig_colors = extract_colors_from_title(orig_lower)
    found_colors = extract_colors_from_title(found_lower)
    
    # Color match bonus/penalty
    color_bonus = 0
    if orig_colors:
        if any(c in found_colors for c in orig_colors):
            color_bonus = 15  # Bonus for matching color
        elif found_colors:
            color_bonus = -20  # Penalty for wrong color
    
    final_score = min(100, max(0, overlap_score + color_bonus))
    return final_score

def extract_product_info(visual_matches, target_brand, allowed_sites, original_title="", pass_type="first"):
    """
    Extract product URLs with SMART validation
    - Brand's own site: 15% similarity (distinguish variants)
    - Marketplaces: 5% similarity + brand verification
    - Balanced selection: Visual rank + title similarity
    """
    results = {}
    for site_key in allowed_sites:
        results[site_key] = {
            "url": "Not Found",
            "price": "Product not available on site",
        }
    
    if not visual_matches:
        return results, 0, 0
    
    brand_matches = 0
    rejected = 0
    rejected_similarity = 0
    
    # Process each match and collect candidates
    candidates = {site_key: [] for site_key in allowed_sites}
    
    for idx, match in enumerate(visual_matches, 1):
        link = match.get("link", "")
        match_title = match.get("title", "")
        
        if not link:
            continue
        
        site_key = identify_site(link)
        if not site_key or site_key not in allowed_sites:
            continue
        
        # Brand verification
        if not check_brand_relaxed_match(match, target_brand, site_key):
            rejected += 1
            continue
        
        # STRICT URL validation
        if not is_valid_product_url(link):
            continue
        
        # Calculate title similarity
        similarity_score = calculate_title_similarity(original_title, match_title)
        
        # Smart thresholds
        is_marketplace = site_key in ['myntra', 'slikk']
        
        if is_marketplace:
            similarity_threshold = 5  # Low threshold for marketplaces
        else:
            similarity_threshold = 15  # Higher threshold for brand sites (distinguish variants)
        
        if similarity_score < similarity_threshold:
            rejected_similarity += 1
            continue
        
        # Extract price
        price = extract_price_from_match(match)
        
        # Add to candidates
        candidates[site_key].append({
            "url": link,
            "price": price,
            "visual_rank": idx,
            "similarity": similarity_score,
            "title": match_title
        })
    
    # Select BEST candidate for each site
    for site_key in allowed_sites:
        if candidates[site_key]:
            is_marketplace = site_key in ['myntra', 'slikk']
            
            if is_marketplace:
                # Marketplace: Trust visual ranking (Google Lens is accurate)
                best_match = min(candidates[site_key], key=lambda x: x['visual_rank'])
            else:
                # Brand site: Balance similarity + visual rank
                # Each rank position = -5% similarity penalty
                best_match = max(candidates[site_key], 
                                key=lambda x: x['similarity'] - (x['visual_rank'] * 5))
            
            results[site_key] = {
                "url": best_match["url"],
                "price": best_match["price"]
            }
            
            brand_matches += 1
            
            # Display result
            site_display = site_key.upper().replace("_", " ")
            rank = best_match["visual_rank"]
            similarity = best_match["similarity"]
            price_display = f"₹{best_match['price']}" if best_match["price"] not in ["Price not displayed in listing", "Product not available on site", "Check site for price"] else "Check site"
            pass_indicator = "🔄" if pass_type == "second" else "✓"
            print(f"      {pass_indicator} {site_display}: Rank #{rank} | Match {similarity:.0f}% | Price: {price_display}")
    
    return results, brand_matches, rejected

def process_products(input_csv, output_csv):
    """
    Main processing function with MULTI-PASS APPROACH for maximum accuracy:
    1. Pass 1: Pure image search
    2. Pass 2: Image + brand + category (for missing sites)
    3. Pass 3: Image + brand + gender + category + color (for tough cases)
    """
    # Read input CSV
    products = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append({
                'style_id': row.get('style_id', ''),
                'brand': row.get('brand', ''),
                'product_title': row.get('product_title', ''),
                'gender': row.get('gender', ''),
                'category': row.get('category', ''),
                'min_price_rupees': row.get('min_price_rupees', ''),
                'image': row.get('first_image_url', '')
            })
    
    # Determine allowed sites based on brand
    brand_name = products[0]['brand'] if products else ''
    allowed_sites = get_allowed_sites(brand_name)
    
    print(f"\n📦 Processing {len(products)} products from '{brand_name}'")
    print(f"🔍 Searching {len(allowed_sites)} sites: {', '.join([s.replace('_', ' ').title() for s in allowed_sites])}")
    print(f"🎯 Strategy: Multi-pass with strict validation for maximum accuracy")
    
    # Prepare CSV output
    fieldnames = ['style_id', 'brand', 'product_title', 'gender', 'category']
    fieldnames.append('klydo_price')
    for site in allowed_sites:
        fieldnames.append(f'{site}_price')
    fieldnames.append('klydo_url')
    for site in allowed_sites:
        fieldnames.append(f'{site}_url')
    
    all_results = []
    
    print("\n" + "="*80)
    print("PASS 1: PURE IMAGE SEARCH (Visual Only)")
    print("="*80)
    
    # PASS 1: Pure image search
    for idx, product in enumerate(products, 1):
        print(f"\n[{idx}/{len(products)}] {product['product_title'][:60]}...")
        
        if not product['image']:
            print("  ⚠ No image URL - Skipping")
            all_results.append({'product': product, 'site_results': {}})
            continue
        
        search_results = search_image_on_serpapi(product['image'])
        
        if not search_results:
            print("  ⚠ No API results")
            all_results.append({'product': product, 'site_results': {}})
            continue
        
        visual_matches = search_results.get("visual_matches", [])
        
        site_results, brand_matches, rejected = extract_product_info(
            visual_matches, 
            product['brand'], 
            allowed_sites, 
            product['product_title'],
            pass_type="first"
        )
        
        sites_found = sum(1 for site_data in site_results.values() if site_data["url"] != "Not Found")
        print(f"  💾 Found on {sites_found}/{len(allowed_sites)} site(s)")
        
        all_results.append({'product': product, 'site_results': site_results})
        
        if idx < len(products):
            time.sleep(1)
    
    # PASS 2: Image + Query for missing sites
    print("\n" + "="*80)
    print("PASS 2: IMAGE + QUERY SEARCH (For Missing Sites)")
    print("="*80)
    
    for idx, result_entry in enumerate(all_results, 1):
        product = result_entry['product']
        existing_results = result_entry['site_results']
        
        # Check which sites are still missing
        sites_missing = [s for s in allowed_sites if existing_results.get(s, {}).get('url') == "Not Found"]
        
        if not sites_missing:
            continue
        
        print(f"\n[{idx}/{len(products)}] 🔄 {product['product_title'][:60]}...")
        print(f"  Missing: {', '.join([s.upper() for s in sites_missing])}")
        
        if not product['image']:
            continue
        
        # Extract color from title for more specific query
        colors = extract_colors_from_title(product['product_title'])
        color_str = colors[0] if colors else ""
        
        # Build query: brand + gender + category + color
        query_parts = [product['brand'], product['gender'], product['category'], color_str]
        query = " ".join([p for p in query_parts if p])
        
        print(f"  Query: {query}")
        
        search_results = search_image_with_query_on_serpapi(product['image'], query)
        
        if not search_results:
            continue
        
        visual_matches = search_results.get("visual_matches", [])
        
        site_results_pass2, _, _ = extract_product_info(
            visual_matches,
            product['brand'],
            sites_missing,
            product['product_title'],
            pass_type="second"
        )
        
        # Update results
        for site_key in sites_missing:
            if site_results_pass2.get(site_key, {}).get('url') != "Not Found":
                existing_results[site_key] = site_results_pass2[site_key]
        
        if idx < len(products):
            time.sleep(1)
    
    # WRITE RESULTS
    print("\n" + "="*80)
    print("WRITING RESULTS")
    print("="*80)
    
    csv_file = open(output_csv, 'w', encoding='utf-8', newline='')
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()
    
    total_sites_found = 0
    for result_entry in all_results:
        product = result_entry['product']
        site_results = result_entry['site_results']
        
        row_data = create_csv_row(product, site_results, allowed_sites)
        writer.writerow(row_data)
        
        sites_found = sum(1 for site_data in site_results.values() if site_data["url"] != "Not Found")
        total_sites_found += sites_found
    
    csv_file.close()
    
    avg_sites = total_sites_found/len(products) if len(products) > 0 else 0
    print(f"\n✅ Processed {len(products)} products | Avg {avg_sites:.1f} sites/product")
    
    # Final coverage report
    print("\n" + "="*80)
    print("FINAL COVERAGE REPORT")
    print("="*80)
    for site_key in allowed_sites:
        found_count = sum(1 for r in all_results if r['site_results'].get(site_key, {}).get('url') != "Not Found")
        coverage = found_count / len(products) if len(products) > 0 else 0
        status = "✅" if coverage >= COVERAGE_THRESHOLD else "⚠️"
        print(f"{status} {site_key.upper().replace('_', ' ')}: {found_count}/{len(products)} ({coverage*100:.0f}%)")

def create_csv_row(product, site_results, allowed_sites):
    """Create CSV row with product info and dynamic columns for each site"""
    klydo_url = f"https://klydo.in/product/{product['style_id']}"
    
    row = {
        'style_id': product['style_id'],
        'brand': product['brand'],
        'product_title': product['product_title'],
        'gender': product['gender'],
        'category': product['category'],
        'klydo_price': product['min_price_rupees'],
        'klydo_url': klydo_url
    }
    
    for site_key in allowed_sites:
        if site_key in site_results:
            url = site_results[site_key]['url']
            price = site_results[site_key]['price']
            row[f'{site_key}_url'] = url
            row[f'{site_key}_price'] = "Check site for price" if url != "Not Found" and price == "Price not displayed in listing" else price
        else:
            row[f'{site_key}_url'] = "Not Found"
            row[f'{site_key}_price'] = "Product not available on site"
    
    return row

# === MAIN EXECUTION ===
if __name__ == "__main__":
    INPUT_FILE = "bear_input.csv"
    OUTPUT_FILE = "bd.csv"
    
    print("\n" + "="*80)
    print("🔍 HIGH-ACCURACY PRODUCT SEARCH v4.0")
    print("="*80)
    print(f"Input: {INPUT_FILE} → Output: {OUTPUT_FILE}")
    print("✅ Multi-pass strategy: Visual → Visual+Query")
    print("✅ Strict URL validation (filters category pages)")
    print("✅ Smart title matching (15% brand sites, 5% marketplaces)")
    print("✅ Color matching bonus/penalty")
    print("✅ Balanced candidate selection")
    print("="*80)
    
    process_products(INPUT_FILE, OUTPUT_FILE)
    
    print("\n✅ ALL DONE!")
    print(f"📄 Check: {OUTPUT_FILE}")
