"""
Storage Module for Amazon Scraper
Handles database models, repositories, and data persistence
"""

from .models import (
    Base, Product, FetchLog, ScrapingSession, PriceHistory, 
    FetchStatus, create_database_engine, create_session_factory
)
from .product_repository import ProductRepository

__all__ = [
    'Base',
    'Product', 
    'FetchLog',
    'ScrapingSession',
    'PriceHistory',
    'FetchStatus',
    'create_database_engine',
    'create_session_factory',
    'ProductRepository',
]
