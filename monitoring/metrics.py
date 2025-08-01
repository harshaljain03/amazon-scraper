"""
Prometheus metrics monitoring module for Amazon Scraper
Exposes comprehensive metrics for monitoring scraping performance
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from threading import Lock
from datetime import datetime, timedelta

from prometheus_client import (
    Counter, Histogram, Gauge, Info, Enum,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)

import structlog

logger = structlog.get_logger(__name__)


# Global metrics instance
_metrics_instance: Optional['ScrapingMetrics'] = None


@dataclass
class ProxyHealthMetrics:
    """Health metrics for a single proxy"""
    ip: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    average_response_time: float = 0.0
    current_block_rate: float = 0.0
    health_score: float = 1.0
    consecutive_failures: int = 0
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    
    def update_success(self, response_time: float):
        """Update metrics after successful request"""
        self.total_requests += 1
        self.successful_requests += 1
        self.last_success_time = datetime.utcnow()
        self.consecutive_failures = 0
        self.response_times.append(response_time)
        self._update_averages()
        self._calculate_health_score()
    
    def update_failure(self, error_type: str = "unknown"):
        """Update metrics after failed request"""
        self.total_requests += 1
        self.failed_requests += 1
        self.last_failure_time = datetime.utcnow()
        self.consecutive_failures += 1
        self._calculate_health_score()
    
    def _update_averages(self):
        """Update average response time"""
        if self.response_times:
            self.average_response_time = sum(self.response_times) / len(self.response_times)
    
    def _calculate_health_score(self):
        """Calculate proxy health score (0.0 to 1.0)"""
        if self.total_requests == 0:
            self.health_score = 1.0
            return
        
        success_rate = self.successful_requests / self.total_requests
        
        # Penalize consecutive failures
        consecutive_penalty = min(self.consecutive_failures * 0.1, 0.5)
        
        # Penalize slow response times
        response_penalty = 0.0
        if self.average_response_time > 10.0:  # More than 10 seconds
            response_penalty = min((self.average_response_time - 10.0) / 20.0, 0.3)
        
        # Calculate final score
        self.health_score = max(0.0, success_rate - consecutive_penalty - response_penalty)
        
        # Update block rate (recent failure rate)
        recent_failures = sum(1 for rt in list(self.response_times)[-20:] if rt == -1)  # -1 for failures
        self.current_block_rate = recent_failures / min(len(self.response_times), 20) if self.response_times else 0.0


class ScrapingMetrics:
    """
    Central metrics collector for Amazon scraping operations
    Integrates with Prometheus for monitoring and alerting
    """
    
    def __init__(self, registry: CollectorRegistry = None):
        """
        Initialize metrics collector
        
        Args:
            registry: Optional Prometheus registry (uses default if None)
        """
        self.registry = registry or CollectorRegistry()
        self._lock = Lock()
        
        # Proxy health tracking
        self.proxy_health: Dict[str, ProxyHealthMetrics] = {}
        
        # Initialize Prometheus metrics
        self._init_prometheus_metrics()
        
        # Application info
        self.app_start_time = time.time()
        
        logger.info("Scraping metrics collector initialized")
    
    def _init_prometheus_metrics(self):
        """Initialize all Prometheus metrics"""
        
        # Request counters
        self.total_requests = Counter(
            'scraper_requests_total',
            'Total number of scraping requests',
            ['status', 'proxy_ip', 'target_domain'],
            registry=self.registry
        )
        
        self.successful_requests = Counter(
            'scraper_requests_successful_total',
            'Total number of successful requests',
            ['proxy_ip', 'target_domain'],
            registry=self.registry
        )
        
        self.failed_requests = Counter(
            'scraper_requests_failed_total',
            'Total number of failed requests',
            ['proxy_ip', 'target_domain', 'error_type'],
            registry=self.registry
        )
        
        # Response time histogram
        self.response_time_histogram = Histogram(
            'scraper_response_time_seconds',
            'Response time distribution',
            ['proxy_ip', 'target_domain'],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float('inf')],
            registry=self.registry
        )
        
        # Proxy metrics
        self.proxy_health_score = Gauge(
            'scraper_proxy_health_score',
            'Health score for each proxy (0.0 to 1.0)',
            ['proxy_ip'],
            registry=self.registry
        )
        
        self.proxy_block_rate = Gauge(
            'scraper_proxy_block_rate',
            'Current block rate for each proxy',
            ['proxy_ip'],
            registry=self.registry
        )
        
        self.proxy_response_time = Gauge(
            'scraper_proxy_avg_response_time_seconds',
            'Average response time for each proxy',
            ['proxy_ip'],
            registry=self.registry
        )
        
        self.active_proxies = Gauge(
            'scraper_active_proxies_count',
            'Number of currently active proxies',
            registry=self.registry
        )
        
        # CAPTCHA metrics
        self.captcha_encounters = Counter(
            'scraper_captcha_encounters_total',
            'Total CAPTCHA encounters',
            ['captcha_type', 'proxy_ip'],
            registry=self.registry
        )
        
        self.captcha_solve_success = Counter(
            'scraper_captcha_solved_total',
            'Successfully solved CAPTCHAs',
            ['captcha_type'],
            registry=self.registry
        )
        
        # Product metrics
        self.products_scraped = Counter(
            'scraper_products_scraped_total',
            'Total products scraped',
            ['category', 'source'],
            registry=self.registry
        )
        
        self.products_updated = Counter(
            'scraper_products_updated_total',
            'Total products updated in database',
            registry=self.registry
        )
        
        self.products_created = Counter(
            'scraper_products_created_total',
            'Total new products created in database',
            registry=self.registry
        )
        
        # Rate limiting metrics
        self.rate_limit_hits = Counter(
            'scraper_rate_limit_hits_total',
            'Total rate limit hits',
            ['proxy_ip'],
            registry=self.registry
        )
        
        # System metrics
        self.memory_usage = Gauge(
            'scraper_memory_usage_bytes',
            'Current memory usage in bytes',
            registry=self.registry
        )
        
        self.cpu_usage = Gauge(
            'scraper_cpu_usage_percent',
            'Current CPU usage percentage',
            registry=self.registry
        )
        
        # Uptime
        self.uptime_seconds = Gauge(
            'scraper_uptime_seconds',
            'Application uptime in seconds',
            registry=self.registry
        )
        
        # Application info
        self.app_info = Info(
            'scraper_info',
            'Application information',
            registry=self.registry
        )
        self.app_info.info({
            'version': '1.0.0',
            'python_version': '.'.join(str(x) for x in __import__('sys').version_info[:3]),
            'start_time': str(int(self.app_start_time))
        })
    
    def record_request_attempt(self, url: str, proxy_ip: str, user_agent: str):
        """Record a request attempt"""
        domain = self._extract_domain(url)
        self.total_requests.labels(
            status='attempted',
            proxy_ip=proxy_ip,
            target_domain=domain
        ).inc()
    
    def record_request_success(self, url: str, response_time: float, 
                              status_code: int, proxy_ip: str):
        """Record successful request"""
        domain = self._extract_domain(url)
        
        # Update counters
        self.total_requests.labels(
            status='success',
            proxy_ip=proxy_ip,
            target_domain=domain
        ).inc()
        
        self.successful_requests.labels(
            proxy_ip=proxy_ip,
            target_domain=domain
        ).inc()
        
        # Update histogram
        self.response_time_histogram.labels(
            proxy_ip=proxy_ip,
            target_domain=domain
        ).observe(response_time)
        
        # Update proxy health
        with self._lock:
            if proxy_ip not in self.proxy_health:
                self.proxy_health[proxy_ip] = ProxyHealthMetrics(ip=proxy_ip)
            
            self.proxy_health[proxy_ip].update_success(response_time)
            self._update_proxy_gauges(proxy_ip)
    
    def record_request_failure(self, url: str, error_type: str, proxy_ip: str, 
                              error_details: str = None):
        """Record failed request"""
        domain = self._extract_domain(url)
        
        # Update counters
        self.total_requests.labels(
            status='failure',
            proxy_ip=proxy_ip,
            target_domain=domain
        ).inc()
        
        self.failed_requests.labels(
            proxy_ip=proxy_ip,
            target_domain=domain,
            error_type=error_type
        ).inc()
        
        # Update proxy health
        with self._lock:
            if proxy_ip not in self.proxy_health:
                self.proxy_health[proxy_ip] = ProxyHealthMetrics(ip=proxy_ip)
            
            self.proxy_health[proxy_ip].update_failure(error_type)
            self._update_proxy_gauges(proxy_ip)
    
    def record_captcha_encounter(self, captcha_type: str, proxy_ip: str = 'unknown'):
        """Record CAPTCHA encounter"""
        self.captcha_encounters.labels(
            captcha_type=captcha_type,
            proxy_ip=proxy_ip
        ).inc()
    
    def record_captcha_solved(self, captcha_type: str):
        """Record successfully solved CAPTCHA"""
        self.captcha_solve_success.labels(
            captcha_type=captcha_type
        ).inc()
    
    def record_products_scraped(self, count: int, category: str = 'unknown', 
                               source: str = 'amazon'):
        """Record products scraped"""
        self.products_scraped.labels(
            category=category,
            source=source
        ).inc(count)
    
    def record_products_stored(self, created: int, updated: int):
        """Record products stored in database"""
        self.products_created.inc(created)
        self.products_updated.inc(updated)
    
    def record_rate_limit_hit(self, proxy_ip: str):
        """Record rate limit hit"""
        self.rate_limit_hits.labels(proxy_ip=proxy_ip).inc()
    
    def update_system_metrics(self):
        """Update system resource metrics"""
        try:
            import psutil
            
            # Memory usage
            memory_info = psutil.virtual_memory()
            process = psutil.Process()
            self.memory_usage.set(process.memory_info().rss)
            
            # CPU usage
            cpu_percent = psutil.cpu_percent()
            self.cpu_usage.set(cpu_percent)
            
            # Uptime
            uptime = time.time() - self.app_start_time
            self.uptime_seconds.set(uptime)
            
        except ImportError:
            logger.warning("psutil not available, skipping system metrics")
    
    def _update_proxy_gauges(self, proxy_ip: str):
        """Update proxy-specific gauges"""
        if proxy_ip in self.proxy_health:
            health = self.proxy_health[proxy_ip]
            
            self.proxy_health_score.labels(proxy_ip=proxy_ip).set(health.health_score)
            self.proxy_block_rate.labels(proxy_ip=proxy_ip).set(health.current_block_rate)
            self.proxy_response_time.labels(proxy_ip=proxy_ip).set(health.average_response_time)
    
    def update_active_proxies_count(self, count: int):
        """Update active proxies count"""
        self.active_proxies.set(count)
    
    def get_proxy_health_summary(self) -> Dict[str, Any]:
        """Get summary of proxy health metrics"""
        with self._lock:
            return {
                ip: {
                    'total_requests': health.total_requests,
                    'success_rate': health.successful_requests / max(health.total_requests, 1),
                    'health_score': health.health_score,
                    'block_rate': health.current_block_rate,
                    'avg_response_time': health.average_response_time,
                    'consecutive_failures': health.consecutive_failures,
                    'last_success': health.last_success_time.isoformat() if health.last_success_time else None,
                    'last_failure': health.last_failure_time.isoformat() if health.last_failure_time else None,
                }
                for ip, health in self.proxy_health.items()
            }
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get human-readable metrics summary"""
        # Update system metrics
        self.update_system_metrics()
        
        # Calculate totals
        total_requests = sum(
            sample.value for sample in self.total_requests.collect()[0].samples
        )
        
        successful_requests = sum(
            sample.value for sample in self.successful_requests.collect()[0].samples
        )
        
        failed_requests = sum(
            sample.value for sample in self.failed_requests.collect()[0].samples
        )
        
        return {
            'uptime_seconds': time.time() - self.app_start_time,
            'total_requests': total_requests,
            'successful_requests': successful_requests,
            'failed_requests': failed_requests,
            'success_rate': successful_requests / max(total_requests, 1),
            'active_proxies': len(self.proxy_health),
            'healthy_proxies': sum(
                1 for health in self.proxy_health.values() 
                if health.health_score > 0.5
            ),
            'proxy_health': self.get_proxy_health_summary(),
        }
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except Exception:
            return 'unknown'
    
    def export_metrics(self) -> str:
        """Export metrics in Prometheus format"""
        # Update system metrics before export
        self.update_system_metrics()
        
        # Update active proxies count
        healthy_count = sum(
            1 for health in self.proxy_health.values() 
            if health.health_score > 0.3
        )
        self.update_active_proxies_count(healthy_count)
        
        return generate_latest(self.registry)


def init_metrics(registry: CollectorRegistry = None) -> ScrapingMetrics:
    """Initialize global metrics instance"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = ScrapingMetrics(registry)
    return _metrics_instance


def get_metrics_instance() -> Optional[ScrapingMetrics]:
    """Get the global metrics instance"""
    return _metrics_instance
