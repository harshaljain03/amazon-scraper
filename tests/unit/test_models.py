"""
Unit tests for database models
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from storage.models import (
    Base, Product, PriceHistory, FetchLog, ScrapingSession, 
    FetchStatus, create_database_engine, create_session_factory
)


class TestDatabaseModels:
    """Test cases for SQLAlchemy models"""
    
    @pytest.fixture(scope='function')
    def db_session(self):
        """Create in-memory database session for testing"""
        engine = create_engine('sqlite:///:memory:', echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        yield session
        
        session.close()
    
    def test_product_model_creation(self, db_session):
        """Test Product model creation and basic operations"""
        product = Product(
            asin='B08N5WRWNW',
            title='Test Product',
            url='https://amazon.com/dp/B08N5WRWNW',
            price='$99.99',
            price_numeric=Decimal('99.99'),
            rating=4.5,
            review_count=1000,
            prime_eligible=True,
            sponsored=False
        )
        
        db_session.add(product)
        db_session.commit()
        
        # Verify product was saved
        saved_product = db_session.query(Product).filter_by(asin='B08N5WRWNW').first()
        assert saved_product is not None
        assert saved_product.title == 'Test Product'
        assert saved_product.price_numeric == Decimal('99.99')
        assert saved_product.rating == 4.5
        assert saved_product.prime_eligible is True
        assert saved_product.id is not None  # UUID should be generated
    
    def test_product_unique_asin_constraint(self, db_session):
        """Test that ASIN must be unique"""
        product1 = Product(
            asin='B08DUPLICATE',
            title='Product 1',
            url='https://amazon.com/dp/B08DUPLICATE'
        )
        
        product2 = Product(
            asin='B08DUPLICATE',  # Same ASIN
            title='Product 2',
            url='https://amazon.com/dp/B08DUPLICATE'
        )
        
        db_session.add(product1)
        db_session.commit()
        
        db_session.add(product2)
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    def test_product_to_dict(self, db_session):
        """Test Product to_dict method"""
        product = Product(
            asin='B08TESTDICT',
            title='Test Dictionary Product',
            url='https://amazon.com/test',
            price='$49.99',
            price_numeric=Decimal('49.99'),
            category='Electronics',
            brand='TestBrand'
        )
        
        db_session.add(product)
        db_session.commit()
        
        product_dict = product.to_dict()
        
        assert isinstance(product_dict, dict)
        assert product_dict['asin'] == 'B08TESTDICT'
        assert product_dict['title'] == 'Test Dictionary Product'
        assert product_dict['price_numeric'] == 49.99  # Should be float
        assert product_dict['category'] == 'Electronics'
        assert 'id' in product_dict
    
    def test_price_history_model(self, db_session):
        """Test PriceHistory model creation and relationship"""
        # Create product first
        product = Product(
            asin='B08PRICETEST',
            title='Price Test Product',
            url='https://amazon.com/price-test'
        )
        db_session.add(product)
        db_session.commit()
        
        # Create price history entry
        price_history = PriceHistory(
            product_id=product.id,
            asin=product.asin,
            price='$79.99',
            price_numeric=Decimal('79.99'),
            availability='In Stock',
            prime_eligible=True
        )
        
        db_session.add(price_history)
        db_session.commit()
        
        # Verify relationship
        saved_product = db_session.query(Product).filter_by(asin='B08PRICETEST').first()
        assert len(saved_product.price_history) == 1
        assert saved_product.price_history[0].price == '$79.99'
        assert saved_product.price_history[0].price_numeric == Decimal('79.99')
    
    def test_fetch_log_model(self, db_session):
        """Test FetchLog model creation"""
        fetch_log = FetchLog(
            url='https://amazon.com/s?k=test',
            proxy_ip='192.168.1.100',
            user_agent='Mozilla/5.0 (Test Agent)',
            status=FetchStatus.SUCCESS,
            response_code=200,
            response_time=1.5,
            session_id='test_session_123'
        )
        
        db_session.add(fetch_log)
        db_session.commit()
        
        # Verify fetch log was saved
        saved_log = db_session.query(FetchLog).filter_by(session_id='test_session_123').first()
        assert saved_log is not None
        assert saved_log.url == 'https://amazon.com/s?k=test'
        assert saved_log.status == FetchStatus.SUCCESS
        assert saved_log.response_code == 200
        assert saved_log.response_time == 1.5
    
    def test_fetch_log_to_dict(self, db_session):
        """Test FetchLog to_dict method"""
        fetch_log = FetchLog(
            url='https://amazon.com/test-dict',
            status=FetchStatus.FAILURE,
            error_details='Connection timeout',
            timestamp=datetime.now(timezone.utc)
        )
        
        db_session.add(fetch_log)
        db_session.commit()
        
        log_dict = fetch_log.to_dict()
        
        assert isinstance(log_dict, dict)
        assert log_dict['url'] == 'https://amazon.com/test-dict'
        assert log_dict['status'] == 'failure'
        assert log_dict['error_details'] == 'Connection timeout'
        assert 'timestamp' in log_dict
        assert 'id' in log_dict
    
    def test_scraping_session_model(self, db_session):
        """Test ScrapingSession model creation and properties"""
        session = ScrapingSession(
            session_id='session_test_123',
            status='running',
            search_queries=['test query 1', 'test query 2'],
            scraper_config={'headless': True, 'timeout': 30},
            total_urls=10,
            successful_scrapes=8,
            failed_scrapes=2,
            products_found=25
        )
        
        db_session.add(session)
        db_session.commit()
        
        # Test properties
        assert session.success_rate == 0.8  # 8/10
        assert session.duration is not None  # Should calculate from started_at
        
        # Verify saved data
        saved_session = db_session.query(ScrapingSession).filter_by(
            session_id='session_test_123'
        ).first()
        
        assert saved_session is not None
        assert saved_session.search_queries == ['test query 1', 'test query 2']
        assert saved_session.scraper_config == {'headless': True, 'timeout': 30}
        assert saved_session.success_rate == 0.8
    
    def test_scraping_session_to_dict(self, db_session):
        """Test ScrapingSession to_dict method"""
        session = ScrapingSession(
            session_id='dict_test_session',
            status='completed',
            total_urls=5,
            successful_scrapes=5,
            failed_scrapes=0,
            ended_at=datetime.now(timezone.utc)
        )
        
        db_session.add(session)
        db_session.commit()
        
        session_dict = session.to_dict()
        
        assert isinstance(session_dict, dict)
        assert session_dict['session_id'] == 'dict_test_session'
        assert session_dict['status'] == 'completed'
        assert session_dict['success_rate'] == 1.0  # 5/5
        assert 'duration' in session_dict
        assert 'started_at' in session_dict
        assert 'ended_at' in session_dict
    
    def test_fetch_status_enum(self):
        """Test FetchStatus enum values"""
        assert FetchStatus.SUCCESS.value == 'success'
        assert FetchStatus.FAILURE.value == 'failure'
        assert FetchStatus.TIMEOUT.value == 'timeout'
        assert FetchStatus.BLOCKED.value == 'blocked'
        assert FetchStatus.RATE_LIMITED.value == 'rate_limited'
        assert FetchStatus.CAPTCHA.value == 'captcha'
        assert FetchStatus.RETRY.value == 'retry'
    
    def test_json_encoded_dict_field(self, db_session):
        """Test JSONEncodedDict field type"""
        product = Product(
            asin='B08JSONTEST',
            title='JSON Test Product',
            url='https://amazon.com/json-test',
            dimensions={'length': 10, 'width': 5, 'height': 2},
            features=['Feature 1', 'Feature 2', 'Feature 3']
        )
        
        db_session.add(product)
        db_session.commit()
        
        # Retrieve and verify JSON fields
        saved_product = db_session.query(Product).filter_by(asin='B08JSONTEST').first()
        
        assert isinstance(saved_product.dimensions, dict)
        assert saved_product.dimensions['length'] == 10
        assert isinstance(saved_product.features, list)
        assert len(saved_product.features) == 3
        assert 'Feature 1' in saved_product.features
    
    def test_database_indexes(self, db_session):
        """Test that database indexes work correctly"""
        # Create multiple products with different attributes
        products_data = [
            {'asin': 'B08INDEX01', 'category': 'Electronics', 'rating': 4.5},
            {'asin': 'B08INDEX02', 'category': 'Electronics', 'rating': 4.0},
            {'asin': 'B08INDEX03', 'category': 'Books', 'rating': 3.5},
            {'asin': 'B08INDEX04', 'category': 'Electronics', 'rating': 4.8},
        ]
        
        for data in products_data:
            product = Product(
                asin=data['asin'],
                title=f"Product {data['asin']}",
                url=f"https://amazon.com/dp/{data['asin']}",
                category=data['category'],
                rating=data['rating']
            )
            db_session.add(product)
        
        db_session.commit()
        
        # Test indexed queries
        electronics_products = db_session.query(Product).filter(
            Product.category == 'Electronics'
        ).all()
        assert len(electronics_products) == 3
        
        high_rated_products = db_session.query(Product).filter(
            Product.rating >= 4.5
        ).all()
        assert len(high_rated_products) == 2


class TestDatabaseUtilities:
    """Test database utility functions"""
    
    def test_create_database_engine(self):
        """Test database engine creation"""
        engine = create_database_engine('sqlite:///:memory:')
        
        assert engine is not None
        assert str(engine.url) == 'sqlite:///:memory:'
        
        # Test connection
        connection = engine.connect()
        assert connection is not None
        connection.close()
        engine.dispose()
    
    def test_create_session_factory(self):
        """Test session factory creation"""
        engine = create_database_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        
        SessionFactory = create_session_factory(engine)
        session = SessionFactory()
        
        assert session is not None
        
        # Test basic operation
        product = Product(
            asin='B08FACTORY',
            title='Factory Test Product',
            url='https://amazon.com/factory-test'
        )
        session.add(product)
        session.commit()
        
        saved_product = session.query(Product).filter_by(asin='B08FACTORY').first()
        assert saved_product is not None
        assert saved_product.title == 'Factory Test Product'
        
        session.close()
        engine.dispose()
    
    def test_model_relationships(self):
        """Test model relationships work correctly"""
        engine = create_database_engine('sqlite:///:memory:')
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Create product
            product = Product(
                asin='B08RELATION',
                title='Relationship Test Product',
                url='https://amazon.com/relation-test'
            )
            session.add(product)
            session.flush()  # Get ID without committing
            
            # Create multiple price history entries
            for i, price in enumerate([99.99, 89.99, 94.99]):
                price_history = PriceHistory(
                    product_id=product.id,
                    asin=product.asin,
                    price=f'${price}',
                    price_numeric=Decimal(str(price))
                )
                session.add(price_history)
            
            session.commit()
            
            # Test relationship
            saved_product = session.query(Product).filter_by(asin='B08RELATION').first()
            assert len(saved_product.price_history) == 3
            
            # Test reverse relationship
            price_entry = session.query(PriceHistory).filter_by(asin='B08RELATION').first()
            assert price_entry.product.title == 'Relationship Test Product'
            
        finally:
            session.close()
            engine.dispose()
