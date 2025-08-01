from bs4 import BeautifulSoup

def parse_search_results(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    items = soup.select('[data-component-type="s-search-result"]')
    print(f"DEBUG: Found {len(items)} product containers")
    
    # Debug first 3 items to understand structure
    for i, item in enumerate(items[:3]):
        print(f"\n--- DEBUG: Product {i+1} ---")
        
        # Try different title selectors
        title_elem = item.select_one('h2 a span')
        title_elem2 = item.select_one('h2 span')
        title_elem3 = item.select_one('[data-cy="title-recipe-title"]')
        title_elem4 = item.select_one('h2 a')
        
        print(f"Title option 1 (h2 a span): {title_elem.get_text(strip=True) if title_elem else 'None'}")
        print(f"Title option 2 (h2 span): {title_elem2.get_text(strip=True) if title_elem2 else 'None'}")
        print(f"Title option 3 (data-cy): {title_elem3.get_text(strip=True) if title_elem3 else 'None'}")
        print(f"Title option 4 (h2 a text): {title_elem4.get_text(strip=True) if title_elem4 else 'None'}")
        
        # Try different link selectors
        link_elem = item.select_one('h2 a')
        link_elem2 = item.select_one('a[href*="/dp/"]')
        
        print(f"Link option 1 (h2 a): {link_elem['href'] if link_elem else 'None'}")
        print(f"Link option 2 (a[href*=/dp/]): {link_elem2['href'] if link_elem2 else 'None'}")
        
        # Try different price selectors
        price_whole = item.select_one('.a-price-whole')
        price_elem = item.select_one('.a-price .a-offscreen')
        price_elem2 = item.select_one('.a-price-range .a-offscreen')
        
        print(f"Price option 1 (.a-price-whole): {price_whole.get_text(strip=True) if price_whole else 'None'}")
        print(f"Price option 2 (.a-price .a-offscreen): {price_elem.get_text(strip=True) if price_elem else 'None'}")
        print(f"Price option 3 (.a-price-range .a-offscreen): {price_elem2.get_text(strip=True) if price_elem2 else 'None'}")
        
        print("---")
    
    # Updated parsing logic with multiple selector fallbacks
    for item in items:
        # Try multiple title selectors
        name = None
        title_selectors = [
            'h2 a span',
            'h2 span', 
            'h2 a',
            '[data-cy="title-recipe-title"]'
        ]
        
        for selector in title_selectors:
            title_elem = item.select_one(selector)
            if title_elem:
                name = title_elem.get_text(strip=True)
                break
        
        # Try multiple link selectors
        url = None
        link_selectors = ['h2 a', 'a[href*="/dp/"]']
        for selector in link_selectors:
            link_elem = item.select_one(selector)
            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                if href.startswith('/'):
                    url = "https://www.amazon.in" + href
                else:
                    url = href
                break
        
        # Try multiple price selectors
        price = None
        price_selectors = [
            '.a-price .a-offscreen',
            '.a-price-whole',
            '.a-price-range .a-offscreen'
        ]
        
        for selector in price_selectors:
            price_elem = item.select_one(selector)
            if price_elem:
                price = price_elem.get_text(strip=True)
                break
        
        # If no single price found, try whole + fraction
        if not price:
            price_whole = item.select_one('.a-price-whole')
            price_fraction = item.select_one('.a-price-fraction')
            if price_whole and price_fraction:
                price = f"{price_whole.get_text(strip=True)}.{price_fraction.get_text(strip=True)}"
            elif price_whole:
                price = price_whole.get_text(strip=True)
        
        # Rating
        rating = None
        rating_elem = item.select_one('.a-icon-alt')
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            if 'out of' in rating_text:
                rating = rating_text.split(' ')[0]
        
        # Review count
        review_count = None
        review_selectors = [
            '[aria-label*="ratings"]',
            '[aria-label*="rating"]',
            '.a-size-base'
        ]
        
        for selector in review_selectors:
            reviews_elem = item.select_one(selector)
            if reviews_elem:
                review_text = reviews_elem.get_text(strip=True)
                review_count = ''.join(filter(str.isdigit, review_text))
                if review_count:
                    break

        # Only add product if we have at least name and url
        if name and url:
            products.append({
                "name": name,
                "url": url,
                "price": price,
                "rating": rating,
                "num_reviews": review_count,
            })
    
    return products
