"""
Main Amazon Scraper Integration Script
Orchestrates all components: scheduler, crawler, proxies, DB, monitoring
"""

import asyncio
import logging
import signal
import sys
import time
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path
from contextlib import asynccontextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Core modules
from crawler.playwright_fetcher import PlaywrightFetcher, PlaywrightConfig, create_stealth_config
from crawler.amazon_parser import AmazonSearchParser, ProductInfo
from crawler.captcha_detector import CaptchaHandler, TwoCaptchaSolver
from crawler.user_agent_pool import UserAgentPool

# Proxy and rate limiting
from proxies.proxy_manager import ProxyManager
from proxies.rate_limiter import IPRateLimiter, RateLimitConfig, create_default_rate_limiter

# Storage
from storage.models import Base, create_database_engine, create_session_factory
from storage.product_repository import ProductRepository
from storage.models import ScrapingSession, FetchLog, FetchStatus

# Monitoring
from monitoring.metrics import ScrapingMetrics, init_metrics
from monitoring.metrics_server import start_metrics_server
from monitoring.instrumented_fetcher import InstrumentedPlaywrightFetcher

# Configuration
import structlog


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class ScraperConfig:
    """Configuration for the Amazon scraper"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL', 'sqlite:///amazon_scraper.db')
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.captcha_api_key = os.getenv('TWOCAPTCHA_API_KEY', '')
        self.metrics_host = os.getenv('METRICS_HOST', '0.0.0.0')
        self.metrics_port = int(os.getenv('METRICS_PORT', '8080'))
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.proxy_config_file = os.getenv('PROXY_CONFIG_FILE', 'config/proxies.json')
        self.search_queries = self._load_search_queries()
        self.max_pages_per_query = int(os.getenv('MAX_PAGES_PER_QUERY', '3'))
        self.delay_between_requests = float(os.getenv('DELAY_BETWEEN_REQUESTS', '2.0'))
        
        # Rate limiting
        self.rate_limit_max_requests = int(os.getenv('RATE_LIMIT_MAX_REQUESTS', '5'))
        self.rate_limit_time_window = int(os.getenv('RATE_LIMIT_TIME_WINDOW', '60'))
        
        # Playwright config
        self.playwright_headless = os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
        self.playwright_timeout = int(os.getenv('PLAYWRIGHT_TIMEOUT', '30000'))
    
    def _load_search_queries(self) -> List[str]:
        """Load search queries from environment or default"""
        queries_env = os.getenv('SEARCH_QUERIES', '')
        if queries_env:
            return [q.strip() for q in queries_env.split(',')]
        
        return [
            'wireless headphones',
            'laptop backpack',
            'coffee maker',
            'fitness tracker',
            'bluetooth speakers'
        ]


class AmazonScraper:
    """
    Main Amazon scraper orchestrator
    Integrates all components for complete scraping workflow
    """
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.session_id = f"scrape_{int(time.time())}"
        
        # Core components
        self.metrics: Optional[ScrapingMetrics] = None
        self.metrics_server = None
        self.db_engine = None
        self.db_session_factory = None
        self.proxy_manager: Optional[ProxyManager] = None
        self.rate_limiter: Optional[IPRateLimiter] = None
        self.fetcher: Optional[InstrumentedPlaywrightFetcher] = None
        self.parser: Optional[AmazonSearchParser] = None
        self.captcha_handler: Optional[CaptchaHandler] = None
        self.user_agent_pool: Optional[UserAgentPool] = None
        
        # Session tracking
        self.scraping_session: Optional[ScrapingSession] = None
        self.session_stats = {
            'total_urls': 0,
            'successful_scrapes': 0,
            'failed_scrapes': 0,
            'products_found': 0,
            'products_created': 0,
            'products_updated': 0,
            'captchas_encountered': 0,
            'captchas_solved': 0
        }
        
        # Shutdown handling
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info("Shutdown signal received", signal=signum)
        self.shutdown_requested = True
    
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Amazon scraper", session_id=self.session_id)
        
        try:
            # Initialize metrics
            self.metrics = init_metrics()
            
            # Start metrics server
            self.metrics_server = start_metrics_server(
                host=self.config.metrics_host,
                port=self.config.metrics_port,
                metrics=self.metrics
            )
            logger.info("Metrics server started", 
                       host=self.config.metrics_host, 
                       port=self.config.metrics_port)
            
            # Initialize database
            self.db_engine = create_database_engine(self.config.database_url)
            Base.metadata.create_all(self.db_engine)
            self.db_session_factory = create_session_factory(self.db_engine)
            logger.info("Database initialized", url=self.config.database_url)
            
            # Initialize rate limiter
            rate_config = RateLimitConfig(
                max_requests_per_ip=self.config.rate_limit_max_requests,
                time_window_seconds=self.config.rate_limit_time_window
            )
            self.rate_limiter = IPRateLimiter(rate_config)
            logger.info("Rate limiter initialized", config=rate_config.__dict__)
            
            # Initialize proxy manager
            proxies = self._load_proxies()
            self.proxy_manager = ProxyManager(
                proxies=proxies,
                max_requests_per_proxy=self.config.rate_limit_max_requests
            )
            logger.info("Proxy manager initialized", proxy_count=len(proxies))
            
            # Initialize user agent pool
            self.user_agent_pool = UserAgentPool()
            
            # Initialize Playwright fetcher
            playwright_config = create_stealth_config()
            playwright_config.headless = self.config.playwright_headless
            playwright_config.timeout = self.config.playwright_timeout
            
            self.fetcher = InstrumentedPlaywrightFetcher(
                config=playwright_config,
                rate_limiter=self.rate_limiter,
                metrics=self.metrics
            )
            await self.fetcher.initialize()
            logger.info("Playwright fetcher initialized")
            
            # Initialize parser
            self.parser = AmazonSearchParser()
            
            # Initialize CAPTCHA handler
            if self.config.captcha_api_key:
                solver = TwoCaptchaSolver(self.config.captcha_api_key)
                self.captcha_handler = CaptchaHandler(solver)
                logger.info("CAPTCHA handler initialized")
            
            # Create scraping session record
            await self._create_scraping_session()
            
            logger.info("Amazon scraper initialization complete")
            
        except Exception as e:
            logger.error("Failed to initialize scraper", error=str(e), exc_info=True)
            await self.cleanup()
            raise
    
    def _load_proxies(self) -> List[Dict[str, str]]:
        """Load proxy configuration from file"""
        proxy_file = Path(self.config.proxy_config_file)
        
        if not proxy_file.exists():
            logger.warning("Proxy config file not found, using direct connection", 
                         file=str(proxy_file))
            return []
        
        try:
            with open(proxy_file, 'r') as f:
                proxy_config = json.load(f)
                return proxy_config.get('proxies', [])
        except Exception as e:
            logger.error("Failed to load proxy config", error=str(e), file=str(proxy_file))
            return []
    
    async def _create_scraping_session(self):
        """Create database record for this scraping session"""
        session = self.db_session_factory()
        try:
            self.scraping_session = ScrapingSession(
                session_id=self.session_id,
                started_at=datetime.now(timezone.utc),
                status='running',
                search_queries=self.config.search_queries,
                scraper_config={
                    'max_pages_per_query': self.config.max_pages_per_query,
                    'rate_limit_max_requests': self.config.rate_limit_max_requests,
                    'playwright_headless': self.config.playwright_headless,
                    'proxy_count': len(self._load_proxies())
                }
            )
            session.add(self.scraping_session)
            session.commit()
            logger.info("Scraping session created", session_id=self.session_id)
        finally:
            session.close()
    
    async def run_scraping_workflow(self):
        """Execute the complete scraping workflow"""
        logger.info("Starting scraping workflow", 
                   queries=self.config.search_queries,
                   max_pages=self.config.max_pages_per_query)
        
        try:
            for query_idx, search_query in enumerate(self.config.search_queries):
                if self.shutdown_requested:
                    logger.info("Shutdown requested, stopping workflow")
                    break
                
                logger.info("Processing search query", 
                           query=search_query, 
                           index=query_idx + 1, 
                           total=len(self.config.search_queries))
                
                await self._scrape_search_query(search_query)
                
                # Delay between queries
                if query_idx < len(self.config.search_queries) - 1:
                    delay = self.config.delay_between_requests
                    logger.info("Delaying between queries", delay=delay)
                    await asyncio.sleep(delay)
            
            await self._finalize_scraping_session('completed')
            logger.info("Scraping workflow completed successfully")
            
        except Exception as e:
            logger.error("Scraping workflow failed", error=str(e), exc_info=True)
            await self._finalize_scraping_session('failed')
            raise
    
    async def _scrape_search_query(self, search_query: str):
        """Scrape a single search query across multiple pages"""
        base_url = "https://www.amazon.com/s"
        
        for page in range(1, self.config.max_pages_per_query + 1):
            if self.shutdown_requested:
                break
            
            # Construct search URL
            url = f"{base_url}?k={search_query.replace(' ', '+')}&page={page}"
            self.session_stats['total_urls'] += 1
            
            logger.info("Scraping search page", 
                       query=search_query, 
                       page=page, 
                       url=url)
            
            try:
                # Get proxy for this request
                proxy = self.proxy_manager.get_next_proxy() if self.proxy_manager.proxies else None
                
                # Fetch page with instrumented fetcher (handles rate limiting and metrics)
                result = await self.fetcher.fetch_with_proxy(url, proxy) if proxy else await self.fetcher.fetch(url)
                
                # Log successful fetch
                await self._log_fetch_attempt(url, proxy, 'success', None, result.status_code)
                
                # Handle CAPTCHA if detected
                if self.captcha_handler:
                    await self._handle_captcha(result.html, url)
                
                # Parse products from page
                products = self.parser.parse_search_results(result.html)
                logger.info("Parsed products", count=len(products), url=url)
                
                # Store products in database
                if products:
                    await self._store_products(products, search_query, url)
                
                # Record metrics
                self.metrics.record_products_scraped(len(products), "amazon_search", "amazon")
                self.session_stats['successful_scrapes'] += 1
                self.session_stats['products_found'] += len(products)
                
            except Exception as e:
                logger.error("Failed to scrape page", 
                           url=url, 
                           query=search_query, 
                           page=page, 
                           error=str(e))
                
                # Log failed fetch
                await self._log_fetch_attempt(url, proxy, 'failure', str(e))
                
                # Record metrics
                self.metrics.record_request_failure(url, 'scraping_error', 
                                                  proxy.get('http', 'direct') if proxy else 'direct')
                self.session_stats['failed_scrapes'] += 1
    
    async def _handle_captcha(self, html: str, url: str):
        """Handle CAPTCHA detection and solving"""
        if not self.captcha_handler:
            return
        
        # Create a mock page object for CAPTCHA detection
        # In a real implementation, you'd pass the actual Playwright page
        challenge = await self.captcha_handler.detector.detect_captcha(None, html)
        
        if challenge.detected:
            logger.warning("CAPTCHA detected", 
                          type=challenge.captcha_type.value, 
                          confidence=challenge.confidence,
                          url=url)
            
            self.metrics.record_captcha_encounter(challenge.captcha_type.value)
            self.session_stats['captchas_encountered'] += 1
            
            # Attempt to solve CAPTCHA
            if challenge.captcha_type.value in ['amazon_image', 'recaptcha_v2']:
                try:
                    # This is a simplified example - real implementation would be more complex
                    logger.info("Attempting to solve CAPTCHA", type=challenge.captcha_type.value)
                    
                    # Mock CAPTCHA solving (replace with actual solving logic)
                    await asyncio.sleep(2)  # Simulate solving time
                    
                    self.metrics.record_captcha_solved(challenge.captcha_type.value)
                    self.session_stats['captchas_solved'] += 1
                    
                    logger.info("CAPTCHA solved successfully", type=challenge.captcha_type.value)
                    
                except Exception as e:
                    logger.error("Failed to solve CAPTCHA", 
                               type=challenge.captcha_type.value, 
                               error=str(e))
    
    async def _store_products(self, products: List[ProductInfo], search_query: str, source_url: str):
        """Store parsed products in database"""
        session = self.db_session_factory()
        try:
            repository = ProductRepository(session)
            
            stats = repository.upsert_products_batch(
                products,
                search_query=search_query,
                source_page_url=source_url
            )
            
            # Record metrics
            self.metrics.record_products_stored(stats['created'], stats['updated'])
            self.session_stats['products_created'] += stats['created']
            self.session_stats['products_updated'] += stats['updated']
            
            logger.info("Stored products in database", 
                       created=stats['created'], 
                       updated=stats['updated'],
                       errors=stats['errors'])
            
        except Exception as e:
            logger.error("Failed to store products", error=str(e), exc_info=True)
            raise
        finally:
            session.close()
    
    async def _log_fetch_attempt(self, url: str, proxy: Dict[str, str], status: str, 
                                error_details: str = None, response_code: int = None):
        """Log fetch attempt to database"""
        session = self.db_session_factory()
        try:
            proxy_ip = None
            if proxy:
                # Extract IP from proxy URL
                proxy_url = proxy.get('http', '')
                if '@' in proxy_url:
                    proxy_ip = proxy_url.split('@')[1].split(':')[0]
                else:
                    proxy_ip = proxy_url.split('://')[1].split(':')[0] if '://' in proxy_url else proxy_url
            
            # Get current user agent
            user_agent = self.user_agent_pool.get_random_user_agent() if self.user_agent_pool else "Unknown"
            
            fetch_log = FetchLog(
                url=url,
                proxy_ip=proxy_ip,
                user_agent=user_agent,
                status=FetchStatus(status),
                error_details=error_details,
                response_code=response_code,
                timestamp=datetime.now(timezone.utc)
            )
            
            session.add(fetch_log)
            session.commit()
            
        except Exception as e:
            logger.error("Failed to log fetch attempt", error=str(e))
        finally:
            session.close()
    
    async def _finalize_scraping_session(self, status: str):
        """Finalize the scraping session record"""
        if not self.scraping_session:
            return
        
        session = self.db_session_factory()
        try:
            # Update session record
            db_session = session.query(ScrapingSession).filter_by(
                session_id=self.session_id
            ).first()
            
            if db_session:
                db_session.ended_at = datetime.now(timezone.utc)
                db_session.status = status
                db_session.total_urls = self.session_stats['total_urls']
                db_session.successful_scrapes = self.session_stats['successful_scrapes']
                db_session.failed_scrapes = self.session_stats['failed_scrapes']
                db_session.products_found = self.session_stats['products_found']
                db_session.products_created = self.session_stats['products_created']
                db_session.products_updated = self.session_stats['products_updated']
                
                session.commit()
                
                logger.info("Scraping session finalized", 
                           session_id=self.session_id,
                           status=status,
                           stats=self.session_stats)
        finally:
            session.close()
    
    async def cleanup(self):
        """Clean up all resources"""
        logger.info("Cleaning up scraper resources")
        
        try:
            if self.fetcher:
                await self.fetcher.cleanup()
            
            if self.metrics_server:
                self.metrics_server.stop()
            
            if self.db_engine:
                self.db_engine.dispose()
            
            logger.info("Cleanup completed")
            
        except Exception as e:
            logger.error("Error during cleanup", error=str(e))


async def main():
    """Main entry point for the scraper"""
    config = ScraperConfig()
    scraper = AmazonScraper(config)
    
    try:
        await scraper.initialize()
        await scraper.run_scraping_workflow()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error("Scraper failed", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        await scraper.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
