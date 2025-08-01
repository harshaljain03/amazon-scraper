from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import sys
import os
from datetime import datetime
import signal
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawler.scraper import scrape_category
from data_pipeline.database import DatabaseManager
from data_pipeline.queue import QueueManager
from monitoring.metrics import metrics
from monitoring.alerts import alert_manager

class ScrapingScheduler:
    def __init__(self):
        self.scheduler = BlockingScheduler()
        self.db_manager = None
        self.queue_manager = None
        self.running = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\nReceived signal {signum}. Shutting down scheduler...")
        self.stop()
        
    def _initialize_services(self):
        """Initialize database and queue services"""
        try:
            self.db_manager = DatabaseManager()
            self.db_manager.create_tables()
            print("✅ Database initialized successfully")
            
            self.queue_manager = QueueManager()
            print("✅ Queue manager initialized successfully")
            
            # Start metrics server if not already running
            metrics.start_metrics_server()
            print("✅ Metrics server initialized")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize services: {e}")
            return False
    
    def scheduled_scrape_job(self):
        """Main scheduled scraping job"""
        job_start_time = datetime.now()
        print(f"\n=== Starting scheduled scrape at {job_start_time} ===")
        
        # Define scraping jobs
        scraping_jobs = [
            {
                'url': 'https://www.amazon.in/s?k=laptop',
                'category': 'laptops',
                'max_pages': 2  # Reduced for stability
            },
            {
                'url': 'https://www.amazon.in/s?k=smartphone',
                'category': 'smartphones', 
                'max_pages': 2
            },
            {
                'url': 'https://www.amazon.in/s?k=headphones',
                'category': 'headphones',
                'max_pages': 2
            }
        ]
        
        total_products = 0
        successful_jobs = 0
        
        for job in scraping_jobs:
            try:
                print(f"\n--- Scraping {job['category'].upper()} ---")
                
                # Record request start
                metrics.record_request('started', job['category'])
                
                # Scrape category
                products = scrape_category(
                    category_url=job['url'],
                    max_pages=job['max_pages'],
                    use_proxy=False,
                    db_manager=self.db_manager,
                    category_name=job['category']
                )
                
                # Record metrics
                if products:
                    metrics.record_products_scraped(len(products), job['category'])
                    metrics.record_request('success', job['category'])
                    total_products += len(products)
                    successful_jobs += 1
                    print(f"✅ Scraped {len(products)} products from {job['category']}")
                else:
                    metrics.record_request('failed', job['category'])
                    print(f"❌ No products found for {job['category']}")
                
                # Add delay between categories to be respectful
                time.sleep(10)
                
            except Exception as e:
                print(f"❌ Error scraping {job['category']}: {e}")
                metrics.record_error('scraping_failed')
                metrics.record_request('failed', job['category'])
                
                # Send alert for failed scraping
                try:
                    alert_manager.send_email_alert(
                        f"Scraping Failed: {job['category']}", 
                        f"Error: {str(e)}"
                    )
                except:
                    print("Failed to send alert email")
        
        job_end_time = datetime.now()
        duration = job_end_time - job_start_time
        
        print(f"\n=== Scheduled scrape completed ===")
        print(f"Duration: {duration}")
        print(f"Total products: {total_products}")
        print(f"Successful jobs: {successful_jobs}/{len(scraping_jobs)}")
        
        # Record job completion metrics
        metrics.record_request('job_completed', 'scheduler')
        
        # Health check
        try:
            alert_manager.check_scraper_health(self.db_manager)
        except Exception as e:
            print(f"Health check failed: {e}")
    
    def quick_health_check(self):
        """Quick health check job"""
        try:
            print("Running health check...")
            alert_manager.check_scraper_health(self.db_manager)
            metrics.record_request('health_check', 'system')
        except Exception as e:
            print(f"Health check failed: {e}")
            metrics.record_error('health_check_failed')
    
    def add_jobs(self):
        """Add scheduled jobs"""
        # Main scraping job - every 6 hours
        self.scheduler.add_job(
            func=self.scheduled_scrape_job,
            trigger=CronTrigger(hour='*/6', minute=0),  # Every 6 hours at minute 0
            id='main_scraping_job',
            name='Amazon Product Scraping',
            replace_existing=True,
            misfire_grace_time=600  # 10 minutes grace time
        )
        
        # Health check every hour
        self.scheduler.add_job(
            func=self.quick_health_check,
            trigger=CronTrigger(minute=0),  # Every hour at minute 0
            id='health_check',
            name='Health Check',
            replace_existing=True,
            misfire_grace_time=300  # 5 minutes grace time
        )
        
        # Optional: Quick test job every 30 minutes for testing
        self.scheduler.add_job(
            func=lambda: print(f"Scheduler alive at {datetime.now()}"),
            trigger=IntervalTrigger(minutes=30),
            id='heartbeat',
            name='Scheduler Heartbeat',
            replace_existing=True
        )
    
    def start(self):
        """Start the scheduler"""
        if not self._initialize_services():
            print("❌ Failed to initialize services. Exiting.")
            return False
            
        try:
            self.add_jobs()
            self.running = True
            
            print("\n=== SCHEDULER STARTED ===")
            print("Jobs scheduled:")
            for job in self.scheduler.get_jobs():
                print(f"  📅 {job.name}: {job.trigger}")
            
            print(f"\n🔧 Monitor at: http://localhost:8000/metrics")
            print(f"🗄️  Database: http://localhost:8080")
            print(f"📊 Grafana: http://localhost:3000")
            print("\nPress Ctrl+C to stop scheduler")
            
            # Run one immediate scrape for testing
            print("\n🚀 Running initial scrape job...")
            self.scheduled_scrape_job()
            
            # Start the scheduler
            self.scheduler.start()
            
        except KeyboardInterrupt:
            print("\n⏹️  Scheduler stopped by user")
        except Exception as e:
            print(f"❌ Scheduler error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the scheduler gracefully"""
        if self.running and self.scheduler.running:
            print("🛑 Shutting down scheduler...")
            self.scheduler.shutdown(wait=True)
            self.running = False
            print("✅ Scheduler stopped")

if __name__ == "__main__":
    scheduler = ScrapingScheduler()
    scheduler.start()
