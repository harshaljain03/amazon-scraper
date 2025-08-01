"""
Database Models for Amazon Scraper
SQLAlchemy models for products, fetch logs, and scraping sessions
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum as PyEnum
import json

from sqlalchemy import (
    create_engine, Column, String, Text, Integer, Float, Boolean, 
    DateTime, JSON, Enum, Index, ForeignKey, Numeric, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator, VARCHAR

import structlog

logger = structlog.get_logger(__name__)

# Create declarative base
Base = declarative_base()


class FetchStatus(PyEnum):
    """Status of fetch operations"""
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    CAPTCHA = "captcha"
    RETRY = "retry"


class JSONEncodedDict(TypeDecorator):
    """Custom type for storing JSON data"""
    impl = VARCHAR
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value


class Product(Base):
    """Product model for storing Amazon product information"""
    
    __tablename__ = 'products'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Amazon identifiers
    asin = Column(String(20), unique=True, nullable=False, index=True)
    
    # Basic product information
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    
    # Pricing information
    price = Column(String(50))  # Raw price string from page
    price_numeric = Column(Numeric(10, 2))  # Parsed numeric price
    currency = Column(String(10), default='USD')
    
    # Rating and reviews
    rating = Column(Float)  # 0.0 to 5.0
    review_count = Column(Integer)
    
    # Product details
    image_url = Column(Text)
    category = Column(String(100))
    brand = Column(String(100))
    
    # Availability and shipping
    availability = Column(String(100))
    prime_eligible = Column(Boolean, default=False)
    
    # Marketing flags
    sponsored = Column(Boolean, default=False)
    best_seller = Column(Boolean, default=False)
    amazon_choice = Column(Boolean, default=False)
    
    # Product dimensions and details
    dimensions = Column(JSONEncodedDict)
    weight = Column(String(50))
    features = Column(JSONEncodedDict)  # List of key features
    
    # Seller information
    seller_name = Column(String(200))
    seller_rating = Column(Float)
    fulfilled_by_amazon = Column(Boolean, default=False)
    
    # Search context
    search_query = Column(String(200))  # Query that found this product
    search_rank = Column(Integer)  # Position in search results
    
    # Metadata
    scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), 
                       onupdate=lambda: datetime.now(timezone.utc))
    source_page_url = Column(Text)  # URL where product was found
    
    # Relationships
    price_history = relationship("PriceHistory", back_populates="product", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('ix_products_category_rating', 'category', 'rating'),
        Index('ix_products_price_numeric', 'price_numeric'),
        Index('ix_products_scraped_at', 'scraped_at'),
        Index('ix_products_search_query', 'search_query'),
        Index('ix_products_brand_category', 'brand', 'category'),
    )
    
    def __repr__(self):
        return f"<Product(asin='{self.asin}', title='{self.title[:50]}...')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert product to dictionary"""
        return {
            'id': str(self.id),
            'asin': self.asin,
            'title': self.title,
            'url': self.url,
            'price': self.price,
            'price_numeric': float(self.price_numeric) if self.price_numeric else None,
            'currency': self.currency,
            'rating': self.rating,
            'review_count': self.review_count,
            'image_url': self.image_url,
            'category': self.category,
            'brand': self.brand,
            'availability': self.availability,
            'prime_eligible': self.prime_eligible,
            'sponsored': self.sponsored,
            'best_seller': self.best_seller,
            'amazon_choice': self.amazon_choice,
            'dimensions': self.dimensions,
            'weight': self.weight,
            'features': self.features,
            'seller_name': self.seller_name,
            'seller_rating': self.seller_rating,
            'fulfilled_by_amazon': self.fulfilled_by_amazon,
            'search_query': self.search_query,
            'search_rank': self.search_rank,
            'scraped_at': self.scraped_at.isoformat() if self.scraped_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'source_page_url': self.source_page_url,
        }


class PriceHistory(Base):
    """Price history model for tracking price changes"""
    
    __tablename__ = 'price_history'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign key to product
    product_id = Column(UUID(as_uuid=True), ForeignKey('products.id'), nullable=False)
    asin = Column(String(20), nullable=False, index=True)  # Denormalized for performance
    
    # Price information
    price = Column(String(50), nullable=False)  # Raw price string
    price_numeric = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), default='USD')
    
    # Context
    availability = Column(String(100))
    prime_eligible = Column(Boolean, default=False)
    
    # Timing
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationship
    product = relationship("Product", back_populates="price_history")
    
    # Indexes
    __table_args__ = (
        Index('ix_price_history_asin_recorded', 'asin', 'recorded_at'),
        Index('ix_price_history_price_numeric', 'price_numeric'),
    )
    
    def __repr__(self):
        return f"<PriceHistory(asin='{self.asin}', price='{self.price}', recorded_at='{self.recorded_at}')>"


class FetchLog(Base):
    """Log of all fetch attempts for monitoring and debugging"""
    
    __tablename__ = 'fetch_logs'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Request details
    url = Column(Text, nullable=False)
    proxy_ip = Column(String(45))  # IPv4/IPv6 address
    user_agent = Column(Text)
    
    # Response details
    status = Column(Enum(FetchStatus), nullable=False, index=True)
    response_code = Column(Integer)
    error_details = Column(Text)
    response_time = Column(Float)  # Response time in seconds
    
    # Content information
    content_length = Column(Integer)
    content_type = Column(String(100))
    
    # Timing
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # Context
    session_id = Column(String(100), index=True)  # Link to scraping session
    retry_attempt = Column(Integer, default=0)
    
    # Indexes
    __table_args__ = (
        Index('ix_fetch_logs_timestamp_status', 'timestamp', 'status'),
        Index('ix_fetch_logs_proxy_ip_timestamp', 'proxy_ip', 'timestamp'),
        Index('ix_fetch_logs_session_id', 'session_id'),
    )
    
    def __repr__(self):
        return f"<FetchLog(url='{self.url[:50]}...', status='{self.status}', proxy_ip='{self.proxy_ip}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert fetch log to dictionary"""
        return {
            'id': str(self.id),
            'url': self.url,
            'proxy_ip': self.proxy_ip,
            'user_agent': self.user_agent,
            'status': self.status.value if self.status else None,
            'response_code': self.response_code,
            'error_details': self.error_details,
            'response_time': self.response_time,
            'content_length': self.content_length,
            'content_type': self.content_type,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'session_id': self.session_id,
            'retry_attempt': self.retry_attempt,
        }


class ScrapingSession(Base):
    """Scraping session model for tracking scraping runs"""
    
    __tablename__ = 'scraping_sessions'
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Session identification
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # Timing
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True))
    
    # Status
    status = Column(String(20), default='running')  # running, completed, failed, cancelled
    
    # Configuration
    search_queries = Column(JSONEncodedDict)  # List of search queries
    scraper_config = Column(JSONEncodedDict)  # Scraper configuration used
    
    # Statistics
    total_urls = Column(Integer, default=0)
    successful_scrapes = Column(Integer, default=0)
    failed_scrapes = Column(Integer, default=0)
    products_found = Column(Integer, default=0)
    products_created = Column(Integer, default=0)
    products_updated = Column(Integer, default=0)
    captchas_encountered = Column(Integer, default=0)
    captchas_solved = Column(Integer, default=0)
    
    # Error information
    error_message = Column(Text)
    error_traceback = Column(Text)
    
    # Indexes
    __table_args__ = (
        Index('ix_scraping_sessions_started_at', 'started_at'),
        Index('ix_scraping_sessions_status', 'status'),
    )
    
    def __repr__(self):
        return f"<ScrapingSession(session_id='{self.session_id}', status='{self.status}')>"
    
    @property
    def duration(self) -> Optional[float]:
        """Get session duration in seconds"""
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return None
    
    @property
    def success_rate(self) -> float:
        """Get success rate of scraping attempts"""
        if self.total_urls == 0:
            return 0.0
        return self.successful_scrapes / self.total_urls
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary"""
        return {
            'id': str(self.id),
            'session_id': self.session_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'status': self.status,
            'search_queries': self.search_queries,
            'scraper_config': self.scraper_config,
            'total_urls': self.total_urls,
            'successful_scrapes': self.successful_scrapes,
            'failed_scrapes': self.failed_scrapes,
            'products_found': self.products_found,
            'products_created': self.products_created,
            'products_updated': self.products_updated,
            'captchas_encountered': self.captchas_encountered,
            'captchas_solved': self.captchas_solved,
            'error_message': self.error_message,
            'duration': self.duration,
            'success_rate': self.success_rate,
        }


def create_database_engine(database_url: str, **kwargs):
    """
    Create SQLAlchemy engine with optimal settings
    
    Args:
        database_url: Database connection URL
        **kwargs: Additional engine options
        
    Returns:
        SQLAlchemy Engine instance
    """
    default_options = {
        'pool_size': 20,
        'max_overflow': 0,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'echo': False,
    }
    
    # Merge with provided options
    engine_options = {**default_options, **kwargs}
    
    engine = create_engine(database_url, **engine_options)
    
    logger.info(f"Created database engine for {database_url.split('@')[1] if '@' in database_url else database_url}")
    
    return engine


def create_session_factory(engine):
    """
    Create SQLAlchemy session factory
    
    Args:
        engine: SQLAlchemy Engine instance
        
    Returns:
        Session factory function
    """
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# Migration helpers
def create_all_tables(engine):
    """Create all tables"""
    Base.metadata.create_all(engine)
    logger.info("Created all database tables")


def drop_all_tables(engine):
    """Drop all tables (use with caution!)"""
    Base.metadata.drop_all(engine)
    logger.info("Dropped all database tables")
