from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False)
    url = Column(Text, nullable=False)
    price = Column(String(50))
    rating = Column(Float)
    num_reviews = Column(Integer)
    category = Column(String(100))
    scraped_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'price': self.price,
            'rating': self.rating,
            'num_reviews': self.num_reviews,
            'category': self.category,
            'scraped_at': self.scraped_at.isoformat() if self.scraped_at else None
        }

class DatabaseManager:
    def __init__(self):
        database_url = os.getenv('DATABASE_URL', 'postgresql://username:password@localhost:5432/amazon_scraper')
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self):
        return self.SessionLocal()
    
    def save_products(self, products, category=None):
        session = self.get_session()
        try:
            for product_data in products:
                # Check if product already exists (by URL)
                existing = session.query(Product).filter_by(url=product_data['url']).first()
                
                if existing:
                    # Update existing product
                    existing.name = product_data['name']
                    existing.price = product_data['price']
                    existing.rating = float(product_data['rating']) if product_data['rating'] else None
                    existing.num_reviews = int(product_data['num_reviews']) if product_data['num_reviews'] else None
                    existing.scraped_at = datetime.utcnow()
                else:
                    # Create new product
                    product = Product(
                        name=product_data['name'],
                        url=product_data['url'],
                        price=product_data['price'],
                        rating=float(product_data['rating']) if product_data['rating'] else None,
                        num_reviews=int(product_data['num_reviews']) if product_data['num_reviews'] else None,
                        category=category
                    )
                    session.add(product)
            
            session.commit()
            print(f"Saved {len(products)} products to database")
            
        except Exception as e:
            session.rollback()
            print(f"Error saving products: {e}")
        finally:
            session.close()
    
    def get_products(self, limit=100):
        session = self.get_session()
        try:
            products = session.query(Product).limit(limit).all()
            return [product.to_dict() for product in products]
        finally:
            session.close()
