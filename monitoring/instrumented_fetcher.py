"""
Instrumented fetchers that automatically emit metrics
Integration layer between fetchers and monitoring
"""

import time
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

from crawler.http_fetcher import HTTPFetcher, AsyncHTTPFetcher, FetchResult, HTTPFetchError
from crawler.playwright_fetcher import PlaywrightFetcher, PlaywrightConfig
from monitoring.metrics import get_metrics_instance, ScrapingMetrics
from proxies.rate_limiter import RateLimitExceeded, IPRateLimiter

logger = logging.getLogger(__name__)


class InstrumentedHTTPFetcher(HTTPFetcher):
    """HTTP Fetcher with automatic metrics instrumentation"""
    
    def __init__(self, metrics: ScrapingMetrics = None, rate_limiter: IPRateLimiter = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = metrics or get_metrics_instance()
        self.rate_limiter = rate_limiter
    
    def fetch(self, url: str, headers: Dict[str, str] = None) -> FetchResult:
        """Fetch with automatic metrics recording"""
        proxy_ip = self._get_proxy_ip()
        user_agent = self.session.headers.get('User-Agent', 'unknown')
        
        # Record attempt
        self.metrics.record_request_attempt(url, proxy_ip, user_agent)
        
        start_time = time.time()
        
        try:
            # Apply rate limiting if available
            if self.rate_limiter and proxy_ip != 'direct':
                # This would be async in a real implementation
                pass
            
            result = super().fetch(url, headers)
            response_time = time.time() - start_time
            
            # Record success
            self.metrics.record_request_success(
                url=url,
                response_time=response_time,
                status_code=result.status_code,
                proxy_ip=proxy_ip
            )
            
            return result
            
        except RateLimitExceeded as e:
            # Record rate limit hit
            self.metrics.record_rate_limit_hit(proxy_ip)
            self.metrics.record_request_failure(
                url=url,
                error_type='rate_limited',
                proxy_ip=proxy_ip,
                error_details=str(e)
            )
            raise
            
        except HTTPFetchError as e:
            # Record failure with specific error type
            error_type = self._classify_error(e)
            self.metrics.record_request_failure(
                url=url,
                error_type=error_type,
                proxy_ip=proxy_ip,
                error_details=str(e)
            )
            raise
            
        except Exception as e:
            # Record unexpected error
            self.metrics.record_request_failure(
                url=url,
                error_type='unexpected_error',
                proxy_ip=proxy_ip,
                error_details=str(e)
            )
            raise
    
    def fetch_with_proxy(self, url: str, proxy: Dict[str, str], 
                        headers: Dict[str, str] = None) -> FetchResult:
        """Fetch with proxy and metrics recording"""
        proxy_ip = self._extract_proxy_ip(proxy)
        user_agent = self.session.headers.get('User-Agent', 'unknown')
        
        # Record attempt
        self.metrics.record_request_attempt(url, proxy_ip, user_agent)
        
        start_time = time.time()
        
        try:
            result = super().fetch_with_proxy(url, proxy, headers)
            response_time = time.time() - start_time
            
            # Record success
            self.metrics.record_request_success(
                url=url,
                response_time=response_time,
                status_code=result.status_code,
                proxy_ip=proxy_ip
            )
            
            return result
            
        except RateLimitExceeded as e:
            # Record rate limit hit
            self.metrics.record_rate_limit_hit(proxy_ip)
            self.metrics.record_request_failure(
                url=url,
                error_type='rate_limited',
                proxy_ip=proxy_ip,
                error_details=str(e)
            )
            raise
            
        except HTTPFetchError as e:
            error_type = self._classify_error(e)
            self.metrics.record_request_failure(
                url=url,
                error_type=error_type,
                proxy_ip=proxy_ip,
                error_details=str(e)
            )
            raise
            
        except Exception as e:
            self.metrics.record_request_failure(
                url=url,
                error_type='unexpected_error',
                proxy_ip=proxy_ip,
                error_details=str(e)
            )
            raise
    
    def _get_proxy_ip(self) -> str:
        """Extract current proxy IP from session"""
        proxies = getattr(self.session, 'proxies', {})
        if proxies:
            proxy_url = proxies.get('http') or proxies.get('https', '')
            return self._extract_proxy_ip({'http': proxy_url})
        return 'direct'
    
    def _extract_proxy_ip(self, proxy: Dict[str, str]) -> str:
        """Extract IP from proxy configuration"""
        proxy_url = proxy.get('http') or proxy.get('https', '')
        if not proxy_url:
            return 'direct'
        
        try:
            parsed = urlparse(proxy_url)
            return parsed.hostname or 'unknown'
        except Exception:
            return 'unknown'
    
    def _classify_error(self, error: HTTPFetchError) -> str:
        """Classify error type for metrics"""
        error_str = str(error).lower()
        
        if 'timeout' in error_str:
            return 'timeout'
        elif 'connection' in error_str:
            return 'connection_error'
        elif hasattr(error, 'status_code') and error.status_code:
            if error.status_code == 403:
                return 'blocked'
            elif error.status_code == 404:
                return 'not_found'
            elif error.status_code == 429:
                return 'rate_limited'
            elif 400 <= error.status_code < 500:
                return 'client_error'
            elif 500 <= error.status_code < 600:
                return 'server_error'
        
        return 'unknown_error'


class InstrumentedPlaywrightFetcher(PlaywrightFetcher):
    """Playwright Fetcher with automatic metrics instrumentation"""
    
    def __init__(self, config: PlaywrightConfig = None, metrics: ScrapingMetrics = None, 
                 rate_limiter: IPRateLimiter = None, *args, **kwargs):
        super().__init__(config=config, rate_limiter=rate_limiter, *args, **kwargs)
        self.metrics = metrics or get_metrics_instance()
    
    async def fetch(self, url: str, proxy: Dict[str, str] = None, **kwargs) -> FetchResult:
        """Fetch with automatic metrics recording"""
        proxy_ip = self._extract_proxy_ip(proxy) if proxy else 'direct'
        user_agent = self.config.user_agent or 'unknown'
        
        # Record attempt
        self.metrics.record_request_attempt(url, proxy_ip, user_agent)
        
        start_time = time.time()
        
        try:
            result = await super().fetch(url, proxy, **kwargs)
            response_time = time.time() - start_time
            
            # Record success
            self.metrics.record_request_success(
                url=url,
                response_time=response_time,
                status_code=result.status_code,
                proxy_ip=proxy_ip
            )
            
            return result
            
        except Exception as e:
            error_type = self._classify_playwright_error(e)
            self.metrics.record_request_failure(
                url=url,
                error_type=error_type,
                proxy_ip=proxy_ip,
                error_details=str(e)
            )
            raise
    
    def _extract_proxy_ip(self, proxy: Dict[str, str]) -> str:
        """Extract IP from proxy configuration"""
        if not proxy:
            return 'direct'
        
        proxy_url = proxy.get('http') or proxy.get('https', '')
        if not proxy_url:
            return 'direct'
        
        try:
            parsed = urlparse(proxy_url)
            return parsed.hostname or 'unknown'
        except Exception:
            return 'unknown'
    
    def _classify_playwright_error(self, error: Exception) -> str:
        """Classify Playwright error type"""
        error_str = str(error).lower()
        
        if 'timeout' in error_str:
            return 'timeout'
        elif 'net::err_connection' in error_str:
            return 'connection_error'
        elif 'net::err_proxy' in error_str:
            return 'proxy_error'
        elif 'navigation' in error_str:
            return 'navigation_error'
        else:
            return 'playwright_error'
