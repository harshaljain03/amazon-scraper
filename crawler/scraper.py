from playwright.sync_api import sync_playwright
from .parser import parse_search_results
from .proxies import load_proxies, get_random_proxy, get_working_proxy
import time
import random
import sys
import os

# Add parent directory to path for importing data_pipeline and monitoring
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_pipeline.database import DatabaseManager
from data_pipeline.queue import QueueManager
from monitoring.metrics import metrics

def fetch_page(url, proxy=None):
    """Fetch a page using Playwright with optional proxy support"""
    with sync_playwright() as p:
        # Configure launch arguments
        launch_args = {"headless": True}
        if proxy:
            launch_args["proxy"] = {"server": proxy}
        
        browser = None
        try:
            browser = p.chromium.launch(**launch_args)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/115.0.0.0 Safari/537.36",
                locale="en-US",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            print(f"Fetching {url} using proxy={proxy} ...")
            
            # Navigate with retry logic
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            
            # Wait a bit for dynamic content
            page.wait_for_timeout(2000)
            
            html = page.content()
            browser.close()
            
            # Record successful request
            metrics.record_request('success', 'unknown')
            
            return html
            
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            if browser:
                browser.close()
            
            # Record failed request
            metrics.record_error('fetch_failed')
            metrics.record_request('failed', 'unknown')
            
            return None

@metrics.time_request
def scrape_category(category_url, max_pages=2, use_proxy=False, db_manager=None, category_name="unknown"):
    """Scrape multiple pages from a category with metrics tracking"""
    all_products = []
    
    # Record scraping start
    metrics.record_request('started', category_name)
    
    # Load proxies if needed
    proxies = load_proxies() if use_proxy else []
    working_proxy = None
    
    if use_proxy and proxies:
        working_proxy = get_working_proxy(proxies)
        if working_proxy:
            print(f"Using working proxy: {working_proxy}")
            metrics.update_active_proxies(len(proxies))
        else:
            print("No working proxies found, proceeding without proxy")
            metrics.record_error('no_working_proxies')
            metrics.update_active_proxies(0)
    
    for page_num in range(1, max_pages + 1):
        # Construct URL for pagination
        if page_num == 1:
            url = category_url
        else:
            separator = "&" if "?" in category_url else "?"
            url = f"{category_url}{separator}page={page_num}"
        
        # Random delay between requests
        if page_num > 1:
            delay = random.uniform(2, 5)
            print(f"Waiting {delay:.2f} seconds before next request...")
            time.sleep(delay)
        
        # Fetch page with retry logic
        max_retries = 3
        retry_count = 0
        html = None
        
        while retry_count < max_retries and not html:
            proxy_to_use = working_proxy if use_proxy else None
            html = fetch_page(url, proxy=proxy_to_use)
            
            if not html:
                retry_count += 1
                print(f"Retry {retry_count}/{max_retries} for page {page_num}")
                
                # Try with different proxy if available
                if use_proxy and proxies and retry_count < max_retries:
                    working_proxy = get_working_proxy(proxies)
                    if working_proxy:
                        print(f"Trying with new proxy: {working_proxy}")
                    else:
                        print("No more working proxies available")
                        break
                
                # Exponential backoff
                time.sleep(2 ** retry_count)
        
        if html:
            try:
                products = parse_search_results(html)
                print(f"Found {len(products)} products on page {page_num}")
                all_products.extend(products)
                
                # Record metrics for successful scraping
                metrics.record_products_scraped(len(products), category_name)
                
                # Save to database after each page if db_manager is provided
                if db_manager and products:
                    db_manager.save_products(products, category=category_name)
                    metrics.record_database_operation('save_products')
                    
            except Exception as e:
                print(f"Error parsing products from page {page_num}: {e}")
                metrics.record_error('parsing_failed')
                
        else:
            print(f"Failed to fetch page {page_num} after {max_retries} retries")
            metrics.record_error('page_fetch_failed')
    
    # Record final metrics
    if all_products:
        metrics.record_request('completed', category_name)
    else:
        metrics.record_request('failed', category_name)
    
    return all_products

def scrape_with_queue(queue_manager, db_manager):
    """Process scraping jobs from queue with metrics tracking"""
    print("Starting queue worker...")
    metrics.record_request('queue_worker_started', 'system')
    
    while True:
        try:
            job = queue_manager.get_job(timeout=30)
            if job:
                print(f"Processing job: {job}")
                
                url = job.get('url')
                category = job.get('category', 'unknown')
                max_pages = job.get('max_pages', 1)
                use_proxy = job.get('use_proxy', False)
                
                # Scrape the category
                products = scrape_category(
                    category_url=url,
                    max_pages=max_pages,
                    use_proxy=use_proxy,
                    db_manager=db_manager,
                    category_name=category
                )
                
                # Add result to results queue
                result = {
                    'job': job,
                    'products_found': len(products),
                    'status': 'completed' if products else 'failed',
                    'timestamp': time.time()
                }
                queue_manager.add_result(result)
                
                print(f"Job completed: {len(products)} products found")
                
            else:
                print("No jobs in queue, waiting...")
                time.sleep(10)
                
        except KeyboardInterrupt:
            print("Queue worker stopped by user")
            break
        except Exception as e:
            print(f"Error in queue worker: {e}")
            metrics.record_error('queue_worker_error')
            time.sleep(5)

def run_health_check(db_manager):
    """Run a health check on the scraper system"""
    try:
        print("Running health check...")
        
        # Test database connection
        session = db_manager.get_session()
        session.close()
        print("✅ Database connection: OK")
        
        # Test basic scraping functionality
        test_url = "https://www.amazon.in/s?k=test"
        html = fetch_page(test_url, proxy=None)
        if html and len(html) > 1000:
            print("✅ Basic scraping: OK")
        else:
            print("❌ Basic scraping: FAILED")
            return False
        
        # Test metrics system
        metrics.record_request('health_check', 'system')
        print("✅ Metrics system: OK")
        
        return True
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        metrics.record_error('health_check_failed')
        return False

if __name__ == "__main__":
    print("Starting Amazon product scraper with database and monitoring...")
    
    # START METRICS SERVER FIRST
    try:
        metrics.start_metrics_server()
        print("✅ Metrics server started successfully")
    except Exception as e:
        print(f"❌ Failed to start metrics server: {e}")
    
    # Initialize database and queue
    try:
        db_manager = DatabaseManager()
        queue_manager = QueueManager()
        
        # Create database tables
        db_manager.create_tables()
        print("✅ Database initialized successfully")
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        print("Please check your database connection settings in .env file")
        print("Make sure Docker containers are running: docker-compose up -d")
        exit(1)
    
    # Run health check
    if not run_health_check(db_manager):
        print("❌ Health check failed. Please check your configuration.")
        exit(1)
    
    # Configuration
    category_urls = {
        'laptops': 'https://www.amazon.in/s?k=laptop',
        'smartphones': 'https://www.amazon.in/s?k=smartphone', 
        'headphones': 'https://www.amazon.in/s?k=headphones'
    }
    
    max_pages = 3
    use_proxy = False  # Set to True to use proxies
    
    # Choose execution mode
    execution_mode = "direct"  # or "queue" or "single"
    
    if execution_mode == "single":
        # Single category scraping mode for testing
        print("Running in single category test mode...")
        category_name = 'laptops'
        category_url = category_urls[category_name]
        
        all_products = scrape_category(
            category_url=category_url, 
            max_pages=2,  # Reduced for testing
            use_proxy=use_proxy,
            db_manager=db_manager,
            category_name=category_name
        )
        
        print(f"\n=== SINGLE CATEGORY SCRAPING COMPLETE ===")
        print(f"Category: {category_name}")
        print(f"Total products found: {len(all_products)}")
        
        if all_products:
            print(f"\nFirst 3 products scraped:")
            for i, product in enumerate(all_products[:3], 1):
                print(f"{i}. {product['name'][:60]}...")
                print(f"   Price: {product['price']}")
                print(f"   Rating: {product['rating']}")
                print(f"   Reviews: {product['num_reviews']}")
                print()
    
    elif execution_mode == "direct":
        # Direct scraping mode for all categories
        print("Running in direct multi-category scraping mode...")
        
        total_products_all = 0
        
        for category_name, category_url in category_urls.items():
            print(f"\n--- Scraping {category_name.upper()} ---")
            
            all_products = scrape_category(
                category_url=category_url, 
                max_pages=max_pages, 
                use_proxy=use_proxy,
                db_manager=db_manager,
                category_name=category_name
            )
            
            total_products_all += len(all_products)
            print(f"Completed {category_name}: {len(all_products)} products")
            
            # Delay between categories
            if category_name != list(category_urls.keys())[-1]:  # Not the last category
                delay = random.uniform(10, 20)
                print(f"Waiting {delay:.2f} seconds before next category...")
                time.sleep(delay)
        
        print(f"\n=== ALL CATEGORIES SCRAPING COMPLETE ===")
        print(f"Total products found across all categories: {total_products_all}")
            
    elif execution_mode == "queue":
        # Queue-based processing mode
        print("Running in queue processing mode...")
        
        # Clear existing queue
        queue_manager.clear_queue()
        
        # Add jobs to queue
        sample_jobs = []
        for category_name, category_url in category_urls.items():
            job = {
                'url': category_url,
                'category': category_name,
                'max_pages': max_pages,
                'use_proxy': use_proxy
            }
            sample_jobs.append(job)
            queue_manager.add_job(job)
        
        print(f"Added {len(sample_jobs)} jobs to queue")
        print(f"Queue size: {queue_manager.get_queue_size()}")
        print("Press Ctrl+C to stop queue processing")
        
        # Start processing jobs
        scrape_with_queue(queue_manager, db_manager)
    
    # Show database stats and create backup
    try:
        print("\n=== DATABASE SUMMARY ===")
        recent_products = db_manager.get_products(limit=10)
        
        if recent_products:
            print(f"Recent products from database:")
            for product in recent_products:
                print(f"- {product['name'][:50]}... | {product['price']} | ⭐{product['rating']} | {product['category']}")
        
        # Save backup file
        backup_products = db_manager.get_products(limit=1000)
        if backup_products:
            with open("scraped_products_backup.txt", "w", encoding="utf-8") as f:
                for product in backup_products:
                    f.write(f"Name: {product['name']}\n")
                    f.write(f"Price: {product['price']}\n")
                    f.write(f"Rating: {product['rating']}\n")
                    f.write(f"Reviews: {product['num_reviews']}\n")
                    f.write(f"URL: {product['url']}\n")
                    f.write(f"Category: {product['category']}\n")
                    f.write(f"Scraped At: {product['scraped_at']}\n")
                    f.write("-" * 80 + "\n")
            
            print(f"✅ Backup saved to scraped_products_backup.txt ({len(backup_products)} products)")
        
    except Exception as e:
        print(f"❌ Error creating database summary/backup: {e}")
    
    # Final metrics and monitoring info
    print(f"\n=== MONITORING INFO ===")
    print(f"📊 Prometheus metrics: http://localhost:8000/metrics")
    print(f"🗄️  Database (pgAdmin): http://localhost:8080")
    print(f"📈 Grafana dashboards: http://localhost:3000")
    
    print(f"\n=== SCRAPER COMPLETED ===")
