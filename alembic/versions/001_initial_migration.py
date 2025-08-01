"""Initial migration for Amazon Scraper

Revision ID: 001_initial_migration
Revises: 
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001_initial_migration'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial tables for Amazon Scraper"""
    
    # Create products table
    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asin', sa.String(length=20), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('price', sa.String(length=50), nullable=True),
        sa.Column('price_numeric', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=True, default='USD'),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('review_count', sa.Integer(), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('brand', sa.String(length=100), nullable=True),
        sa.Column('availability', sa.String(length=100), nullable=True),
        sa.Column('prime_eligible', sa.Boolean(), nullable=True, default=False),
        sa.Column('sponsored', sa.Boolean(), nullable=True, default=False),
        sa.Column('best_seller', sa.Boolean(), nullable=True, default=False),
        sa.Column('amazon_choice', sa.Boolean(), nullable=True, default=False),
        sa.Column('dimensions', sa.VARCHAR(), nullable=True),
        sa.Column('weight', sa.String(length=50), nullable=True),
        sa.Column('features', sa.VARCHAR(), nullable=True),
        sa.Column('seller_name', sa.String(length=200), nullable=True),
        sa.Column('seller_rating', sa.Float(), nullable=True),
        sa.Column('fulfilled_by_amazon', sa.Boolean(), nullable=True, default=False),
        sa.Column('search_query', sa.String(length=200), nullable=True),
        sa.Column('search_rank', sa.Integer(), nullable=True),
        sa.Column('scraped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_page_url', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asin')
    )
    
    # Create indexes for products
    op.create_index('ix_products_asin', 'products', ['asin'])
    op.create_index('ix_products_category_rating', 'products', ['category', 'rating'])
    op.create_index('ix_products_price_numeric', 'products', ['price_numeric'])
    op.create_index('ix_products_scraped_at', 'products', ['scraped_at'])
    op.create_index('ix_products_search_query', 'products', ['search_query'])
    op.create_index('ix_products_brand_category', 'products', ['brand', 'category'])
    
    # Create price_history table
    op.create_table(
        'price_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asin', sa.String(length=20), nullable=False),
        sa.Column('price', sa.String(length=50), nullable=False),
        sa.Column('price_numeric', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=True, default='USD'),
        sa.Column('availability', sa.String(length=100), nullable=True),
        sa.Column('prime_eligible', sa.Boolean(), nullable=True, default=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for price_history
    op.create_index('ix_price_history_asin', 'price_history', ['asin'])
    op.create_index('ix_price_history_asin_recorded', 'price_history', ['asin', 'recorded_at'])
    op.create_index('ix_price_history_price_numeric', 'price_history', ['price_numeric'])
    op.create_index('ix_price_history_recorded_at', 'price_history', ['recorded_at'])
    
    # Create fetch_logs table
    op.create_table(
        'fetch_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('proxy_ip', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('SUCCESS', 'FAILURE', 'TIMEOUT', 'BLOCKED', 'RATE_LIMITED', 'CAPTCHA', 'RETRY', name='fetchstatus'), nullable=False),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('error_details', sa.Text(), nullable=True),
        sa.Column('response_time', sa.Float(), nullable=True),
        sa.Column('content_length', sa.Integer(), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('session_id', sa.String(length=100), nullable=True),
        sa.Column('retry_attempt', sa.Integer(), nullable=True, default=0),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for fetch_logs
    op.create_index('ix_fetch_logs_status', 'fetch_logs', ['status'])
    op.create_index('ix_fetch_logs_timestamp', 'fetch_logs', ['timestamp'])
    op.create_index('ix_fetch_logs_timestamp_status', 'fetch_logs', ['timestamp', 'status'])
    op.create_index('ix_fetch_logs_proxy_ip_timestamp', 'fetch_logs', ['proxy_ip', 'timestamp'])
    op.create_index('ix_fetch_logs_session_id', 'fetch_logs', ['session_id'])
    
    # Create scraping_sessions table
    op.create_table(
        'scraping_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', sa.String(length=100), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, default='running'),
        sa.Column('search_queries', sa.VARCHAR(), nullable=True),
        sa.Column('scraper_config', sa.VARCHAR(), nullable=True),
        sa.Column('total_urls', sa.Integer(), nullable=True, default=0),
        sa.Column('successful_scrapes', sa.Integer(), nullable=True, default=0),
        sa.Column('failed_scrapes', sa.Integer(), nullable=True, default=0),
        sa.Column('products_found', sa.Integer(), nullable=True, default=0),
        sa.Column('products_created', sa.Integer(), nullable=True, default=0),
        sa.Column('products_updated', sa.Integer(), nullable=True, default=0),
        sa.Column('captchas_encountered', sa.Integer(), nullable=True, default=0),
        sa.Column('captchas_solved', sa.Integer(), nullable=True, default=0),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_traceback', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id')
    )
    
    # Create indexes for scraping_sessions
    op.create_index('ix_scraping_sessions_session_id', 'scraping_sessions', ['session_id'])
    op.create_index('ix_scraping_sessions_started_at', 'scraping_sessions', ['started_at'])
    op.create_index('ix_scraping_sessions_status', 'scraping_sessions', ['status'])


def downgrade() -> None:
    """Drop all tables"""
    op.drop_table('scraping_sessions')
    op.drop_table('fetch_logs')
    op.drop_table('price_history')
    op.drop_table('products')
    
    # Drop enum type
    sa.Enum(name='fetchstatus').drop(op.get_bind())
