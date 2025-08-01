"""
Unit tests for Amazon parser functionality
"""

import pytest
from unittest.mock import Mock, patch
from bs4 import BeautifulSoup

from crawler.amazon_parser import AmazonSearchParser, ProductInfo
from tests.fixtures.sample_html import (
    SAMPLE_AMAZON_SEARCH_HTML, 
    SAMPLE_PRODUCT_PAGE_HTML,
    get_sample_product_info
)


class TestAmazonSearchParser:
    """Test cases for Amazon search results parser"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.parser = AmazonSearchParser()
        self.sample_products = get_sample_product_info()
    
    def test_parser_initialization(self):
        """Test parser initializes correctly"""
        assert self.parser.base_url == "https://www.amazon.com"
        assert 'product_container' in self.parser.selectors
        assert 'title' in self.parser.selectors
        assert 'price' in self.parser.selectors
    
    def test_parse_search_results_success(self):
        """Test successful parsing of search results"""
        products = self.parser.parse_search_results(SAMPLE_AMAZON_SEARCH_HTML)
        
        assert len(products) == 2
        
        # Test first product
        first_product = products[0]
        assert "Sony WH-1000XM4" in first_product.title
        assert first_product.price == "$248.00"
        assert first_product.rating == 4.4
        assert first_product.num_reviews == 73284
        assert first_product.prime_eligible is True
        assert first_product.sponsored is False
        
        # Test second product
        second_product = products[1]
        assert "Apple AirPods Pro" in second_product.title
        assert second_product.price == "$199.00"
        assert second_product.rating == 4.5
        assert second_product.num_reviews == 89523
        assert second_product.prime_eligible is True
        assert second_product.sponsored is True
    
    def test_parse_empty_html(self):
        """Test parsing empty HTML returns empty list"""
        products = self.parser.parse_search_results("")
        assert products == []
        
        products = self.parser.parse_search_results("<html><body></body></html>")
        assert products == []
    
    def test_parse_malformed_html(self):
        """Test parsing malformed HTML handles gracefully"""
        malformed_html = "<div><span>Broken HTML"
        products = self.parser.parse_search_results(malformed_html)
        assert isinstance(products, list)
    
    def test_extract_asin_from_container(self):
        """Test ASIN extraction from product containers"""
        soup = BeautifulSoup(SAMPLE_AMAZON_SEARCH_HTML, 'lxml')
        containers = soup.select('div[data-component-type="s-search-result"]')
        
        asin1 = self.parser._extract_asin(containers[0])
        assert asin1 == "B08N5WRWNW"
        
        asin2 = self.parser._extract_asin(containers[1])
        assert asin2 == "B0756CYWWD"
    
    def test_extract_title_and_url(self):
        """Test title and URL extraction"""
        soup = BeautifulSoup(SAMPLE_AMAZON_SEARCH_HTML, 'lxml')
        container = soup.select('div[data-component-type="s-search-result"]')[0]
        
        title, url = self.parser._extract_title_and_url(container, "https://www.amazon.com")
        
        assert "Sony WH-1000XM4" in title
        assert "/dp/B08N5WRWNW" in url
        assert url.startswith("https://www.amazon.com")
    
    def test_extract_price_various_formats(self):
        """Test price extraction with various formats"""
        # Test with sample HTML
        soup = BeautifulSoup(SAMPLE_AMAZON_SEARCH_HTML, 'lxml')
        container = soup.select('div[data-component-type="s-search-result"]')[0]
        
        price = self.parser._extract_price(container)
        assert price == "$248.00"
        
        # Test with different price formats
        price_html_variants = [
            '<span class="a-offscreen">$29.99</span>',
            '<span class="a-price-whole">19</span><span class="a-price-fraction">95</span>',
            '<span>€45.50</span>',
            '<span>£12.99</span>'
        ]
        
        for price_html in price_html_variants:
            soup = BeautifulSoup(f'<div>{price_html}</div>', 'lxml')
            price = self.parser._extract_price(soup.find('div'))
            assert price is not None
    
    def test_extract_rating(self):
        """Test rating extraction"""
        soup = BeautifulSoup(SAMPLE_AMAZON_SEARCH_HTML, 'lxml')
        container = soup.select('div[data-component-type="s-search-result"]')[0]
        
        rating = self.parser._extract_rating(container)
        assert rating == 4.4
        
        # Test various rating formats
        rating_html_variants = [
            '<span class="a-icon-alt">4.5 out of 5 stars</span>',
            '<span aria-label="3.8 out of 5 stars">3.8</span>',
            '<span>5.0</span>'
        ]
        
        for rating_html in rating_html_variants:
            soup = BeautifulSoup(f'<div>{rating_html}</div>', 'lxml')
            rating = self.parser._extract_rating(soup.find('div'))
            assert isinstance(rating, float)
            assert 0 <= rating <= 5
    
    def test_extract_review_count(self):
        """Test review count extraction"""
        soup = BeautifulSoup(SAMPLE_AMAZON_SEARCH_HTML, 'lxml')
        container = soup.select('div[data-component-type="s-search-result"]')[0]
        
        review_count = self.parser._extract_review_count(container)
        assert review_count == 73284
        
        # Test various review count formats
        review_html_variants = [
            '<a href="#reviews">1,234</a>',
            '<span>5,678 ratings</span>',
            '<span>(23,456)</span>'
        ]
        
        for review_html in review_html_variants:
            soup = BeautifulSoup(f'<div>{review_html}</div>', 'lxml')
            count = self.parser._extract_review_count(soup.find('div'))
            assert isinstance(count, int)
            assert count > 0
    
    def test_check_prime_eligible(self):
        """Test Prime eligibility detection"""
        soup = BeautifulSoup(SAMPLE_AMAZON_SEARCH_HTML, 'lxml')
        container = soup.select('div[data-component-type="s-search-result"]')[0]
        
        is_prime = self.parser._check_prime_eligible(container)
        assert is_prime is True
        
        # Test non-Prime product
        non_prime_html = '<div><span>Regular shipping</span></div>'
        soup = BeautifulSoup(non_prime_html, 'lxml')
        is_prime = self.parser._check_prime_eligible(soup.find('div'))
        assert is_prime is False
    
    def test_check_sponsored(self):
        """Test sponsored product detection"""
        soup = BeautifulSoup(SAMPLE_AMAZON_SEARCH_HTML, 'lxml')
        
        # First product (not sponsored)
        container1 = soup.select('div[data-component-type="s-search-result"]')[0]
        is_sponsored1 = self.parser._check_sponsored(container1)
        assert is_sponsored1 is False
        
        # Second product (sponsored)
        container2 = soup.select('div[data-component-type="s-search-result"]')[1]
        is_sponsored2 = self.parser._check_sponsored(container2)
        assert is_sponsored2 is True
    
    def test_parse_product_page(self):
        """Test individual product page parsing"""
        product = self.parser.parse_product_page(SAMPLE_PRODUCT_PAGE_HTML)
        
        assert product is not None
        assert "Sony WH-1000XM4" in product.title
        assert product.price == "$248.00"
        assert product.rating == 4.4
        assert product.num_reviews == 73284
        assert product.prime_eligible is True
    
    @pytest.mark.parametrize("base_url,expected_domain", [
        ("https://www.amazon.com", "amazon.com"),
        ("https://www.amazon.co.uk", "amazon.co.uk"),
        ("https://www.amazon.de", "amazon.de"),
    ])
    def test_different_amazon_domains(self, base_url, expected_domain):
        """Test parsing works with different Amazon domains"""
        products = self.parser.parse_search_results(SAMPLE_AMAZON_SEARCH_HTML, base_url)
        
        assert len(products) > 0
        for product in products:
            if product.product_url:
                assert base_url in product.product_url


class TestProductInfo:
    """Test cases for ProductInfo data class"""
    
    def test_product_info_creation(self):
        """Test ProductInfo object creation"""
        product = ProductInfo(
            title="Test Product",
            price="$19.99",
            rating=4.5,
            num_reviews=1000
        )
        
        assert product.title == "Test Product"
        assert product.price == "$19.99"
        assert product.rating == 4.5
        assert product.num_reviews == 1000
        assert product.prime_eligible is False  # Default
        assert product.sponsored is False  # Default
    
    def test_product_info_to_dict(self):
        """Test ProductInfo to dictionary conversion"""
        product = ProductInfo(
            title="Test Product",
            price="$19.99",
            rating=4.5,
            num_reviews=1000,
            prime_eligible=True
        )
        
        product_dict = product.to_dict()
        
        assert isinstance(product_dict, dict)
        assert product_dict['title'] == "Test Product"
        assert product_dict['price'] == "$19.99"
        assert product_dict['rating'] == 4.5
        assert product_dict['num_reviews'] == 1000
        assert product_dict['prime_eligible'] is True
    
    def test_product_info_from_dict(self):
        """Test ProductInfo creation from dictionary"""
        product_dict = {
            'title': "Test Product",
            'price': "$19.99",
            'rating': 4.5,
            'num_reviews': 1000,
            'prime_eligible': True
        }
        
        product = ProductInfo.from_dict(product_dict)
        
        assert product.title == "Test Product"
        assert product.price == "$19.99"
        assert product.rating == 4.5
        assert product.num_reviews == 1000
        assert product.prime_eligible is True


def test_parse_amazon_search_html_convenience_function():
    """Test the convenience function for parsing Amazon search HTML"""
    from crawler.amazon_parser import parse_amazon_search_html
    
    products = parse_amazon_search_html(SAMPLE_AMAZON_SEARCH_HTML)
    
    assert len(products) == 2
    assert all(isinstance(p, ProductInfo) for p in products)
    assert "Sony WH-1000XM4" in products[0].title
    assert "Apple AirPods Pro" in products[1].title
