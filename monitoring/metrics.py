from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time
import threading
from functools import wraps

# Define metrics
REQUESTS_TOTAL = Counter('scraper_requests_total', 'Total scraper requests', ['status', 'category'])
REQUEST_DURATION = Histogram('scraper_request_duration_seconds', 'Request duration')
PRODUCTS_SCRAPED = Counter('products_scraped_total', 'Total products scraped', ['category'])
ACTIVE_PROXIES = Gauge('active_proxies_count', 'Number of active proxies')
SCRAPER_ERRORS = Counter('scraper_errors_total', 'Total scraper errors', ['error_type'])
DATABASE_OPERATIONS = Counter('database_operations_total', 'Database operations', ['operation'])

class MetricsCollector:
    def __init__(self, port=8000):
        self.port = port
        self.server_started = False
        self.server_thread = None
    
    def start_metrics_server(self):
        """Start Prometheus metrics server in a separate thread"""
        if not self.server_started:
            def run_server():
                try:
                    start_http_server(self.port)
                    print(f"Prometheus metrics server started on http://localhost:{self.port}/metrics")
                except Exception as e:
                    print(f"Failed to start metrics server: {e}")
            
            self.server_thread = threading.Thread(target=run_server, daemon=True)
            self.server_thread.start()
            self.server_started = True
            
            # Wait a moment for server to start
            time.sleep(1)
            print(f"Metrics accessible at: http://localhost:{self.port}/metrics")
    
    def record_request(self, status, category='unknown'):
        """Record a scraper request"""
        REQUESTS_TOTAL.labels(status=status, category=category).inc()
    
    def record_products_scraped(self, count, category='unknown'):
        """Record number of products scraped"""
        PRODUCTS_SCRAPED.labels(category=category).inc(count)
    
    def record_error(self, error_type):
        """Record an error"""
        SCRAPER_ERRORS.labels(error_type=error_type).inc()
    
    def record_database_operation(self, operation):
        """Record database operation"""
        DATABASE_OPERATIONS.labels(operation=operation).inc()
    
    def update_active_proxies(self, count):
        """Update active proxy count"""
        ACTIVE_PROXIES.set(count)
    
    def time_request(self, func):
        """Decorator to time function execution"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                REQUEST_DURATION.observe(time.time() - start_time)
                return result
            except Exception as e:
                REQUEST_DURATION.observe(time.time() - start_time)
                raise
        return wrapper

# Global metrics instance
metrics = MetricsCollector()
