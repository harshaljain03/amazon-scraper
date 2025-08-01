"""
Product Repository for Amazon Scraper
Handles product data persistence with optimized queries
"""

import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import re

from sqlalchemy.orm import Session
from sqlalchemy import func, text, and_, or_, desc, asc
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from storage.models import Product, PriceHistory, FetchLog, ScrapingSession, FetchStatus
from crawler.amazon_parser import ProductInfo

import structlog

logger = structlog.get_logger(__name__)


class ProductRepository:
    """
    Repository for product data operations
    Provides high-level interface for product persistence
    """
    
    def __init__(self, session: Session):
        """
        Initialize product repository
        
        Args:
            session: SQLAlchemy session
        """
        self.session = session
    
    def create_product(self, product_info: ProductInfo, **kwargs) -> Product:
        """
        Create a new product from ProductInfo
        
        Args:
            product_info: ProductInfo object
            **kwargs: Additional product attributes
            
        Returns:
            Created Product instance
        """
        try:
            # Parse price
            price_numeric = self._parse_price(product_info.price)
            
            # Extract ASIN from URL if not provided
            asin = self._extract_asin_from_url(product_info.product_url)
            
            # Create product
            product = Product(
                asin=asin,
                title=product_info.title,
                url=product_info.product_url or "",
                price=product_info.price,
                price_numeric=price_numeric,
                rating=product_info.rating,
                review_count=product_info.num_reviews,
                image_url=product_info.image_url,
                prime_eligible=product_info.prime_eligible,
                sponsored=product_info.sponsored,
                availability=product_info.availability,
                brand=product_info.brand,
                category=product_info.category,
                **kwargs
            )
            
            self.session.add(product)
            self.session.flush()  # Get ID without committing
            
            # Create initial price history entry
            if price_numeric:
                self._create_price_history_entry(product, product_info.price, price_numeric)
            
            logger.debug(f"Created product: {asin}")
            return product
            
        except Exception as e:
            logger.error(f"Failed to create product: {e}")
            self.session.rollback()
            raise
    
    def update_product(self, product: Product, product_info: ProductInfo, **kwargs) -> Product:
        """
        Update existing product with new information
        
        Args:
            product: Existing Product instance
            product_info: New ProductInfo data
            **kwargs: Additional attributes to update
            
        Returns:
            Updated Product instance
        """
        try:
            # Parse new price
            new_price_numeric = self._parse_price(product_info.price)
            
            # Check if price changed
            price_changed = (
                new_price_numeric != product.price_numeric and 
                new_price_numeric is not None
            )
            
            # Update product fields
            product.title = product_info.title or product.title
            product.url = product_info.product_url or product.url
            product.price = product_info.price or product.price
            product.price_numeric = new_price_numeric or product.price_numeric
            product.rating = product_info.rating if product_info.rating is not None else product.rating
            product.review_count = product_info.num_reviews if product_info.num_reviews is not None else product.review_count
            product.image_url = product_info.image_url or product.image_url
            product.prime_eligible = product_info.prime_eligible if product_info.prime_eligible is not None else product.prime_eligible
            product.sponsored = product_info.sponsored if product_info.sponsored is not None else product.sponsored
            product.availability = product_info.availability or product.availability
            product.brand = product_info.brand or product.brand
            product.category = product_info.category or product.category
            product.updated_at = datetime.now(timezone.utc)
            
            # Update additional kwargs
            for key, value in kwargs.items():
                if hasattr(product, key) and value is not None:
                    setattr(product, key, value)
            
            # Create price history entry if price changed
            if price_changed:
                self._create_price_history_entry(product, product_info.price, new_price_numeric)
                logger.debug(f"Price changed for {product.asin}: {product.price} -> {product_info.price}")
            
            logger.debug(f"Updated product: {product.asin}")
            return product
            
        except Exception as e:
            logger.error(f"Failed to update product {product.asin}: {e}")
            raise
    
    def upsert_product(self, product_info: ProductInfo, **kwargs) -> Tuple[Product, bool]:
        """
        Create or update product (upsert operation)
        
        Args:
            product_info: ProductInfo object
            **kwargs: Additional product attributes
            
        Returns:
            Tuple of (Product instance, was_created)
        """
        try:
            asin = self._extract_asin_from_url(product_info.product_url)
            
            if not asin:
                raise ValueError(f"Could not extract ASIN from product info: {product_info.title}")
            
            # Try to find existing product
            existing_product = self.session.query(Product).filter_by(asin=asin).first()
            
            if existing_product:
                # Update existing product
                updated_product = self.update_product(existing_product, product_info, **kwargs)
                return updated_product, False
            else:
                # Create new product
                new_product = self.create_product(product_info, **kwargs)
                return new_product, True
                
        except Exception as e:
            logger.error(f"Failed to upsert product: {e}")
            raise
    
    def upsert_products_batch(self, 
                             products: List[ProductInfo], 
                             search_query: str = None,
                             source_page_url: str = None) -> Dict[str, int]:
        """
        Batch upsert multiple products with transaction support
        
        Args:
            products: List of ProductInfo objects
            search_query: Search query that found these products
            source_page_url: URL where products were found
            
        Returns:
            Dictionary with statistics: {'created': int, 'updated': int, 'errors': int}
        """
        stats = {'created': 0, 'updated': 0, 'errors': 0}
        
        try:
            for i, product_info in enumerate(products):
                try:
                    # Additional context
                    kwargs = {}
                    if search_query:
                        kwargs['search_query'] = search_query
                        kwargs['search_rank'] = i + 1
                    if source_page_url:
                        kwargs['source_page_url'] = source_page_url
                    
                    # Upsert product
                    _, was_created = self.upsert_product(product_info, **kwargs)
                    
                    if was_created:
                        stats['created'] += 1
                    else:
                        stats['updated'] += 1
                        
                except Exception as e:
                    logger.error(f"Error upserting product {i}: {e}")
                    stats['errors'] += 1
                    # Continue with next product instead of failing entire batch
            
            # Commit transaction
            self.session.commit()
            
            logger.info(f"Batch upsert completed: {stats}")
            return stats
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Batch upsert failed: {e}")
            stats['errors'] = len(products)
            return stats
    
    def get_product_by_asin(self, asin: str) -> Optional[Product]:
        """Get product by ASIN"""
        return self.session.query(Product).filter_by(asin=asin).first()
    
    def get_products_by_category(self, category: str, limit: int = 100) -> List[Product]:
        """Get products by category"""
        return (self.session.query(Product)
                .filter(Product.category.ilike(f'%{category}%'))
                .order_by(desc(Product.rating), desc(Product.review_count))
                .limit(limit)
                .all())
    
    def get_products_by_price_range(self, min_price: float, max_price: float, limit: int = 100) -> List[Product]:
        """Get products within price range"""
        return (self.session.query(Product)
                .filter(and_(
                    Product.price_numeric >= min_price,
                    Product.price_numeric <= max_price
                ))
                .order_by(asc(Product.price_numeric))
                .limit(limit)
                .all())
    
    def search_products(self, 
                       query: str, 
                       category: str = None,
                       min_rating: float = None,
                       prime_only: bool = False,
                       limit: int = 100) -> List[Product]:
        """
        Search products with filters
        
        Args:
            query: Text to search in title
            category: Category filter
            min_rating: Minimum rating filter
            prime_only: Only Prime eligible products
            limit: Maximum results
            
        Returns:
            List of matching products
        """
        q = self.session.query(Product)
        
        # Text search
        if query:
            q = q.filter(Product.title.ilike(f'%{query}%'))
        
        # Category filter
        if category:
            q = q.filter(Product.category.ilike(f'%{category}%'))
        
        # Rating filter
        if min_rating:
            q = q.filter(Product.rating >= min_rating)
        
        # Prime filter
        if prime_only:
            q = q.filter(Product.prime_eligible == True)
        
        # Order by relevance (rating and review count)
        q = q.order_by(desc(Product.rating), desc(Product.review_count))
        
        return q.limit(limit).all()
    
    def get_price_history(self, asin: str, days: int = 30) -> List[PriceHistory]:
        """
        Get price history for a product
        
        Args:
            asin: Product ASIN
            days: Number of days to look back
            
        Returns:
            List of PriceHistory entries
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        return (self.session.query(PriceHistory)
                .filter(and_(
                    PriceHistory.asin == asin,
                    PriceHistory.recorded_at >= since_date
                ))
                .order_by(PriceHistory.recorded_at)
                .all())
    
    def get_trending_products(self, days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get trending products based on recent activity
        
        Args:
            days: Number of days to analyze
            limit: Maximum results
            
        Returns:
            List of product dictionaries with trend data
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Query for products with recent updates and high ratings
        results = (self.session.query(
                Product,
                func.count(PriceHistory.id).label('price_changes')
            )
            .outerjoin(PriceHistory, and_(
                Product.asin == PriceHistory.asin,
                PriceHistory.recorded_at >= since_date
            ))
            .filter(Product.updated_at >= since_date)
            .group_by(Product.id)
            .order_by(desc('price_changes'), desc(Product.rating), desc(Product.review_count))
            .limit(limit)
            .all())
        
        trending = []
        for product, price_changes in results:
            trending.append({
                **product.to_dict(),
                'price_changes': price_changes,
                'trend_score': price_changes * (product.rating or 0) * (product.review_count or 0) / 1000
            })
        
        return trending
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get repository statistics"""
        try:
            total_products = self.session.query(func.count(Product.id)).scalar() or 0
            
            # Category distribution
            category_stats = (self.session.query(
                    Product.category,
                    func.count(Product.id).label('count')
                )
                .filter(Product.category.isnot(None))
                .group_by(Product.category)
                .order_by(desc('count'))
                .limit(10)
                .all())
            
            # Price distribution
            price_stats = self.session.query(
                func.min(Product.price_numeric).label('min_price'),
                func.max(Product.price_numeric).label('max_price'),
                func.avg(Product.price_numeric).label('avg_price'),
                func.count(Product.price_numeric).label('products_with_price')
            ).filter(Product.price_numeric.isnot(None)).first()
            
            # Recent activity
            recent_date = datetime.now(timezone.utc) - timedelta(days=7)
            recent_products = (self.session.query(func.count(Product.id))
                              .filter(Product.scraped_at >= recent_date)
                              .scalar() or 0)
            
            return {
                'total_products': total_products,
                'recent_products': recent_products,
                'categories': [{'name': cat, 'count': count} for cat, count in category_stats],
                'price_stats': {
                    'min_price': float(price_stats.min_price) if price_stats.min_price else 0,
                    'max_price': float(price_stats.max_price) if price_stats.max_price else 0,
                    'avg_price': float(price_stats.avg_price) if price_stats.avg_price else 0,
                    'products_with_price': price_stats.products_with_price or 0
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {
                'total_products': 0,
                'recent_products': 0,
                'categories': [],
                'price_stats': {
                    'min_price': 0,
                    'max_price': 0,
                    'avg_price': 0,
                    'products_with_price': 0
                }
            }
    
    def _create_price_history_entry(self, product: Product, price_str: str, price_numeric: Decimal):
        """Create price history entry"""
        try:
            price_history = PriceHistory(
                product_id=product.id,
                asin=product.asin,
                price=price_str,
                price_numeric=price_numeric,
                availability=product.availability,
                prime_eligible=product.prime_eligible
            )
            
            self.session.add(price_history)
            logger.debug(f"Created price history entry for {product.asin}: {price_str}")
            
        except Exception as e:
            logger.error(f"Failed to create price history entry: {e}")
    
    def _parse_price(self, price_str: str) -> Optional[Decimal]:
        """Parse price string to decimal"""
        if not price_str:
            return None
        
        try:
            # Remove currency symbols and extra spaces
            cleaned = re.sub(r'[^\d.,]', '', price_str)
            
            # Handle different decimal separators
            if ',' in cleaned and '.' in cleaned:
                # Assume comma is thousands separator
                cleaned = cleaned.replace(',', '')
            elif ',' in cleaned and cleaned.count(',') == 1 and cleaned.index(',') > len(cleaned) - 4:
                # Assume comma is decimal separator
                cleaned = cleaned.replace(',', '.')
            
            return Decimal(cleaned)
            
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Failed to parse price '{price_str}': {e}")
            return None
    
    def _extract_asin_from_url(self, url: str) -> Optional[str]:
        """Extract ASIN from Amazon URL"""
        if not url:
            return None
        
        # Common ASIN patterns in Amazon URLs
        patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'asin=([A-Z0-9]{10})',
            r'/([A-Z0-9]{10})(?:/|\?|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                asin = match.group(1)
                # Validate ASIN format (10 characters, alphanumeric)
                if len(asin) == 10 and asin.isalnum():
                    return asin
        
        logger.warning(f"Could not extract ASIN from URL: {url}")
        return None
    
    def cleanup_old_data(self, days: int = 90):
        """
        Clean up old data to manage database size
        
        Args:
            days: Keep data newer than this many days
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        try:
            # Clean old price history (keep recent entries per product)
            subquery = (self.session.query(
                    PriceHistory.asin,
                    func.max(PriceHistory.recorded_at).label('latest_date')
                )
                .group_by(PriceHistory.asin)
                .subquery())
            
            old_price_history = (self.session.query(PriceHistory)
                                .join(subquery, PriceHistory.asin == subquery.c.asin)
                                .filter(and_(
                                    PriceHistory.recorded_at < cutoff_date,
                                    PriceHistory.recorded_at < subquery.c.latest_date
                                )))
            
            deleted_price_count = old_price_history.count()
            old_price_history.delete(synchronize_session=False)
            
            # Clean old fetch logs
            old_fetch_logs = self.session.query(FetchLog).filter(FetchLog.timestamp < cutoff_date)
            deleted_logs_count = old_fetch_logs.count()
            old_fetch_logs.delete(synchronize_session=False)
            
            # Clean old scraping sessions (keep final state)
            old_sessions = (self.session.query(ScrapingSession)
                           .filter(and_(
                               ScrapingSession.ended_at < cutoff_date,
                               ScrapingSession.status.in_(['completed', 'failed'])
                           )))
            
            deleted_sessions_count = old_sessions.count()
            old_sessions.delete(synchronize_session=False)
            
            self.session.commit()
            
            logger.info(f"Cleanup completed: deleted {deleted_price_count} price history entries, "
                       f"{deleted_logs_count} fetch logs, {deleted_sessions_count} sessions")
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to cleanup old data: {e}")
            raise
