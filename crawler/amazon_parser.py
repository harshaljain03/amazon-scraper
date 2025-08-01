"""
Amazon Search Results Parser
Extracts product information from Amazon search pages and product pages
"""

import re
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ProductInfo:
    """Data class for parsed product information"""
    title: str
    price: Optional[str] = None
    rating: Optional[float] = None
    num_reviews: Optional[int] = None
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    prime_eligible: bool = False
    sponsored: bool = False
    availability: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'title': self.title,
            'price': self.price,
            'rating': self.rating,
            'num_reviews': self.num_reviews,
            'product_url': self.product_url,
            'image_url': self.image_url,
            'prime_eligible': self.prime_eligible,
            'sponsored': self.sponsored,
            'availability': self.availability,
            'brand': self.brand,
            'category': self.category,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProductInfo':
        """Create instance from dictionary"""
        return cls(**data)


class AmazonSearchParser:
    """
    Parser for Amazon search results pages
    Handles various Amazon page layouts and product formats
    """
    
    def __init__(self):
        """Initialize the parser"""
        self.base_url = "https://www.amazon.com"
        
        # CSS selectors for different product elements
        self.selectors = {
            'product_container': [
                'div[data-component-type="s-search-result"]',
                'div[data-asin]',
                '.s-result-item',
                '.sg-col-inner .s-widget-container'
            ],
            'title': [
                'h2 a span',
                '.a-size-mini span',
                '.a-size-base-plus',
                'h2.s-size-mini span',
                '.s-color-base'
            ],
            'price': [
                '.a-price .a-offscreen',
                '.a-price-whole',
                '.a-price .a-price-range .a-offscreen',
                'span.a-price-range'
            ],
            'rating': [
                '[aria-label*="out of 5 stars"] .a-icon-alt',
                '.a-icon-alt',
                '[aria-label*="stars"]'
            ],
            'review_count': [
                '[aria-label*="out of 5 stars"] + a',
                'a[href*="#customerReviews"] span',
                '.a-size-base'
            ],
            'image': [
                '.s-image',
                'img[data-src]',
                'img[src]'
            ],
            'prime': [
                '[aria-label="Prime"]',
                '.a-color-secondary.a-text-strike',
                'i[aria-label="Prime"]',
                '.a-color-prime'
            ],
            'sponsored': [
                '[data-component-type="sp-sponsored-result"]',
                '.AdHolder',
                'span:contains("Sponsored")',
                '[data-creative-detail*="Sponsored"]'
            ]
        }
        
        logger.info("AmazonSearchParser initialized")
    
    def parse_search_results(self, html: str, base_url: str = None) -> List[ProductInfo]:
        """
        Parse Amazon search results HTML and extract product information
        
        Args:
            html: HTML content of Amazon search page
            base_url: Base URL for resolving relative URLs
            
        Returns:
            List of ProductInfo objects
        """
        if base_url is None:
            base_url = self.base_url
        
        soup = BeautifulSoup(html, 'lxml')
        products = []
        
        logger.debug("Starting to parse search results")
        
        # Find all product containers
        product_containers = []
        for selector in self.selectors['product_container']:
            containers = soup.select(selector)
            product_containers.extend(containers)
        
        logger.info(f"Found {len(product_containers)} potential product containers")
        
        for i, container in enumerate(product_containers):
            try:
                product = self._parse_product_container(container, base_url)
                if product and product.title:  # Only add if we have at least a title
                    products.append(product)
                    logger.debug(f"Parsed product {i+1}: {product.title[:50]}...")
                
            except Exception as e:
                logger.warning(f"Failed to parse product container {i+1}: {e}")
                continue
        
        logger.info(f"Successfully parsed {len(products)} products from search results")
        return products
    
    def _parse_product_container(self, container: Tag, base_url: str) -> Optional[ProductInfo]:
        """
        Parse individual product container
        
        Args:
            container: BeautifulSoup tag containing product info
            base_url: Base URL for resolving relative links
            
        Returns:
            ProductInfo object or None if parsing fails
        """
        try:
            # Extract ASIN from container
            asin = self._extract_asin(container)
            
            # Extract title and URL
            title, product_url = self._extract_title_and_url(container, base_url)
            if not title:
                return None
            
            # Extract price
            price = self._extract_price(container)
            
            # Extract rating and reviews
            rating = self._extract_rating(container)
            num_reviews = self._extract_review_count(container)
            
            # Extract image URL
            image_url = self._extract_image_url(container, base_url)
            
            # Check for Prime eligibility
            prime_eligible = self._check_prime_eligible(container)
            
            # Check if sponsored
            sponsored = self._check_sponsored(container)
            
            # Extract additional info
            availability = self._extract_availability(container)
            brand = self._extract_brand(container)
            
            return ProductInfo(
                title=title,
                price=price,
                rating=rating,
                num_reviews=num_reviews,
                product_url=product_url,
                image_url=image_url,
                prime_eligible=prime_eligible,
                sponsored=sponsored,
                availability=availability,
                brand=brand
            )
            
        except Exception as e:
            logger.error(f"Error parsing product container: {e}")
            return None
    
    def _extract_asin(self, container: Tag) -> Optional[str]:
        """Extract ASIN from product container"""
        # Try data-asin attribute first
        asin = container.get('data-asin')
        if asin:
            return asin
        
        # Try to extract from URL
        link = container.find('a', href=True)
        if link:
            href = link['href']
            match = re.search(r'/dp/([A-Z0-9]{10})', href)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_title_and_url(self, container: Tag, base_url: str) -> tuple[Optional[str], Optional[str]]:
        """Extract product title and URL"""
        title = None
        product_url = None
        
        # Look for title in various selectors
        for selector in self.selectors['title']:
            elements = container.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                if text and len(text) > 10:  # Reasonable title length
                    title = text
                    break
            if title:
                break
        
        # Look for product URL
        link_selectors = [
            'h2 a[href]',
            'a[href*="/dp/"]',
            'a[href*="/gp/product/"]'
        ]
        
        for selector in link_selectors:
            link = container.select_one(selector)
            if link and link.get('href'):
                href = link['href']
                if href.startswith('/'):
                    product_url = urljoin(base_url, href)
                else:
                    product_url = href
                break
        
        return title, product_url
    
    def _extract_price(self, container: Tag) -> Optional[str]:
        """Extract product price"""
        for selector in self.selectors['price']:
            elements = container.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                if text and ('$' in text or '€' in text or '£' in text):
                    return text
        
        return None
    
    def _extract_rating(self, container: Tag) -> Optional[float]:
        """Extract product rating"""
        for selector in self.selectors['rating']:
            elements = container.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                
                # Try to extract rating from text like "4.5 out of 5 stars"
                match = re.search(r'(\d+\.?\d*)\s*out of 5', text, re.IGNORECASE)
                if match:
                    try:
                        return float(match.group(1))
                    except ValueError:
                        continue
                
                # Try to extract just a number
                match = re.search(r'^(\d+\.?\d*)$', text)
                if match:
                    try:
                        rating = float(match.group(1))
                        if 0 <= rating <= 5:
                            return rating
                    except ValueError:
                        continue
        
        return None
    
    def _extract_review_count(self, container: Tag) -> Optional[int]:
        """Extract number of reviews"""
        for selector in self.selectors['review_count']:
            elements = container.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                
                # Remove commas and extract numbers
                cleaned_text = re.sub(r'[^\d]', '', text)
                if cleaned_text and cleaned_text.isdigit():
                    return int(cleaned_text)
                
                # Try to find numbers with commas
                match = re.search(r'([\d,]+)', text)
                if match:
                    try:
                        number_str = match.group(1).replace(',', '')
                        return int(number_str)
                    except ValueError:
                        continue
        
        return None
    
    def _extract_image_url(self, container: Tag, base_url: str) -> Optional[str]:
        """Extract product image URL"""
        for selector in self.selectors['image']:
            img = container.select_one(selector)
            if img:
                # Try data-src first (lazy loading)
                src = img.get('data-src') or img.get('src')
                if src:
                    if src.startswith('//'):
                        return 'https:' + src
                    elif src.startswith('/'):
                        return urljoin(base_url, src)
                    elif src.startswith('http'):
                        return src
        
        return None
    
    def _check_prime_eligible(self, container: Tag) -> bool:
        """Check if product is Prime eligible"""
        for selector in self.selectors['prime']:
            element = container.select_one(selector)
            if element:
                text = element.get_text(strip=True).lower()
                if 'prime' in text:
                    return True
                
                # Check aria-label
                aria_label = element.get('aria-label', '').lower()
                if 'prime' in aria_label:
                    return True
        
        return False
    
    def _check_sponsored(self, container: Tag) -> bool:
        """Check if product is sponsored"""
        # Check container attributes
        if container.get('data-component-type') == 'sp-sponsored-result':
            return True
        
        # Check for sponsored text or elements
        for selector in self.selectors['sponsored']:
            if 'contains' in selector:
                # Handle pseudo-selector for text content
                elements = container.find_all(text=re.compile('Sponsored', re.I))
                if elements:
                    return True
            else:
                element = container.select_one(selector)
                if element:
                    return True
        
        # Check for sponsored in text content
        text_content = container.get_text().lower()
        if 'sponsored' in text_content:
            return True
        
        return False
    
    def _extract_availability(self, container: Tag) -> Optional[str]:
        """Extract availability information"""
        availability_selectors = [
            '.a-color-success',
            '.a-color-price', 
            '[data-cy="availability-recipe"]',
            '.a-size-base.a-color-price'
        ]
        
        for selector in availability_selectors:
            element = container.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if any(word in text.lower() for word in ['stock', 'available', 'ships', 'delivery']):
                    return text
        
        return None
    
    def _extract_brand(self, container: Tag) -> Optional[str]:
        """Extract brand information"""
        brand_selectors = [
            '[data-cy="brand-recipe"]',
            '.a-size-base-plus',
            'span[data-attribute="brand"]'
        ]
        
        for selector in brand_selectors:
            element = container.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                if text and len(text) < 50:  # Reasonable brand name length
                    return text
        
        return None
    
    def parse_product_page(self, html: str, base_url: str = None) -> Optional[ProductInfo]:
        """
        Parse individual Amazon product page
        
        Args:
            html: HTML content of product page
            base_url: Base URL for resolving relative URLs
            
        Returns:
            ProductInfo object or None
        """
        if base_url is None:
            base_url = self.base_url
        
        soup = BeautifulSoup(html, 'lxml')
        
        try:
            # Extract title
            title_selectors = [
                '#productTitle',
                '.product-title',
                'h1.a-size-large'
            ]
            
            title = None
            for selector in title_selectors:
                element = soup.select_one(selector)
                if element:
                    title = element.get_text(strip=True)
                    break
            
            if not title:
                return None
            
            # Extract price
            price_selectors = [
                '.a-price .a-offscreen',
                '#priceblock_ourprice',
                '#priceblock_dealprice',
                '.a-price-whole'
            ]
            
            price = None
            for selector in price_selectors:
                element = soup.select_one(selector)
                if element:
                    price = element.get_text(strip=True)
                    break
            
            # Extract rating
            rating_element = soup.select_one('[data-hook="average-star-rating"] .a-icon-alt')
            rating = None
            if rating_element:
                rating_text = rating_element.get_text()
                match = re.search(r'(\d+\.?\d*)', rating_text)
                if match:
                    rating = float(match.group(1))
            
            # Extract review count
            review_element = soup.select_one('[data-hook="total-review-count"]')
            num_reviews = None
            if review_element:
                review_text = review_element.get_text()
                match = re.search(r'([\d,]+)', review_text)
                if match:
                    num_reviews = int(match.group(1).replace(',', ''))
            
            # Extract image
            image_element = soup.select_one('#landingImage, .a-dynamic-image')
            image_url = None
            if image_element:
                src = image_element.get('data-old-hires') or image_element.get('src')
                if src:
                    image_url = urljoin(base_url, src)
            
            # Check Prime eligibility
            prime_eligible = bool(soup.select_one('#primePopover, [data-feature-name="primeEligible"]'))
            
            return ProductInfo(
                title=title,
                price=price,
                rating=rating,
                num_reviews=num_reviews,
                image_url=image_url,
                prime_eligible=prime_eligible
            )
            
        except Exception as e:
            logger.error(f"Error parsing product page: {e}")
            return None


def parse_amazon_search_html(html: str, base_url: str = "https://www.amazon.com") -> List[ProductInfo]:
    """
    Convenience function to parse Amazon search HTML
    
    Args:
        html: HTML content
        base_url: Base URL for Amazon
        
    Returns:
        List of ProductInfo objects
    """
    parser = AmazonSearchParser()
    return parser.parse_search_results(html, base_url)
