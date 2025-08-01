"""
Proxy Manager for Amazon Scraper
Handles proxy rotation, health monitoring, and automatic failover
"""

import random
import logging
import asyncio
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from threading import Lock
from urllib.parse import urlparse
import re

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ProxyInfo:
    """Information about a proxy"""
    http_url: str
    https_url: str = None
    username: str = None
    password: str = None
    ip: str = None
    port: int = None
    country: str = None
    provider: str = None
    
    def __post_init__(self):
        """Extract IP and port from URL"""
        if not self.https_url:
            self.https_url = self.http_url
        
        if not self.ip or not self.port:
            self._extract_ip_port()
    
    def _extract_ip_port(self):
        """Extract IP and port from proxy URL"""
        try:
            parsed = urlparse(self.http_url)
            if parsed.hostname:
                self.ip = parsed.hostname
                self.port = parsed.port or 8080
        except Exception:
            logger.warning(f"Failed to extract IP/port from {self.http_url}")
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for requests library"""
        return {
            'http': self.http_url,
            'https': self.https_url or self.http_url
        }
    
    def get_auth_url(self) -> str:
        """Get URL with authentication if username/password provided"""
        if self.username and self.password:
            parsed = urlparse(self.http_url)
            auth_url = f"{parsed.scheme}://{self.username}:{self.password}@{parsed.netloc}"
            return auth_url
        return self.http_url


@dataclass
class ProxyHealth:
    """Health metrics for a proxy"""
    proxy: ProxyInfo
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    average_response_time: float = 0.0
    last_check_time: Optional[datetime] = None
    is_healthy: bool = True
    block_rate: float = 0.0
    error_types: Dict[str, int] = field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def health_score(self) -> float:
        """Calculate health score (0.0 to 1.0)"""
        if self.total_requests == 0:
            return 1.0
        
        base_score = self.success_rate
        
        # Penalize consecutive failures
        consecutive_penalty = min(self.consecutive_failures * 0.05, 0.3)
        
        # Penalize high response times
        response_penalty = 0.0
        if self.average_response_time > 10.0:
            response_penalty = min((self.average_response_time - 10.0) / 30.0, 0.2)
        
        # Penalize recent failures
        recency_penalty = 0.0
        if self.last_failure_time:
            hours_since_failure = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds() / 3600
            if hours_since_failure < 1:
                recency_penalty = 0.2
            elif hours_since_failure < 6:
                recency_penalty = 0.1
        
        final_score = max(0.0, base_score - consecutive_penalty - response_penalty - recency_penalty)
        return final_score
    
    def update_success(self, response_time: float):
        """Update metrics after successful request"""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.last_success_time = datetime.now(timezone.utc)
        
        # Update average response time (exponential moving average)
        alpha = 0.2
        self.average_response_time = (1 - alpha) * self.average_response_time + alpha * response_time
        
        # Update health status
        self.is_healthy = self.health_score > 0.3
        
        logger.debug(f"Proxy {self.proxy.ip} success - score: {self.health_score:.2f}")
    
    def update_failure(self, error_type: str = "unknown"):
        """Update metrics after failed request"""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        # Track error types
        if error_type not in self.error_types:
            self.error_types[error_type] = 0
        self.error_types[error_type] += 1
        
        # Update block rate based on recent failures
        self._update_block_rate()
        
        # Update health status
        self.is_healthy = self.health_score > 0.3 and self.consecutive_failures < 10
        
        logger.debug(f"Proxy {self.proxy.ip} failure ({error_type}) - score: {self.health_score:.2f}")
    
    def _update_block_rate(self):
        """Update block rate based on recent failure patterns"""
        # Simple heuristic: high block rate if many recent 403/blocked errors
        blocked_errors = (
            self.error_types.get("blocked", 0) + 
            self.error_types.get("403", 0) + 
            self.error_types.get("captcha", 0)
        )
        
        if self.total_requests > 0:
            self.block_rate = min(blocked_errors / self.total_requests, 1.0)
        
        # Increase block rate for consecutive failures
        if self.consecutive_failures > 5:
            self.block_rate = min(self.block_rate + 0.1 * (self.consecutive_failures - 5), 1.0)


class ProxyManager:
    """
    Manages proxy pool with health monitoring and automatic rotation
    """
    
    def __init__(self, 
                 proxies: List[Dict[str, str]] = None,
                 health_check_interval: int = 300,
                 max_requests_per_proxy: int = 100,
                 block_rate_threshold: float = 0.5):
        """
        Initialize proxy manager
        
        Args:
            proxies: List of proxy configurations
            health_check_interval: Seconds between health checks
            max_requests_per_proxy: Max requests per proxy before rotation
            block_rate_threshold: Block rate threshold for marking unhealthy
        """
        self.proxies: List[ProxyInfo] = []
        self.proxy_health: Dict[str, ProxyHealth] = {}
        self.health_check_interval = health_check_interval
        self.max_requests_per_proxy = max_requests_per_proxy
        self.block_rate_threshold = block_rate_threshold
        
        # Thread safety
        self._lock = Lock()
        self._current_index = 0
        
        # Health check task
        self._health_check_task = None
        self._health_check_running = False
        
        # Initialize proxies
        if proxies:
            self._load_proxies(proxies)
        
        logger.info(f"ProxyManager initialized with {len(self.proxies)} proxies")
    
    def _load_proxies(self, proxy_configs: List[Dict[str, str]]):
        """Load proxy configurations"""
        for config in proxy_configs:
            try:
                proxy_info = ProxyInfo(
                    http_url=config.get('http', ''),
                    https_url=config.get('https', ''),
                    username=config.get('username'),
                    password=config.get('password'),
                    country=config.get('country'),
                    provider=config.get('provider')
                )
                
                if proxy_info.http_url:
                    self.proxies.append(proxy_info)
                    
                    # Initialize health tracking
                    self.proxy_health[proxy_info.ip] = ProxyHealth(proxy=proxy_info)
                    
                    logger.debug(f"Loaded proxy: {proxy_info.ip}:{proxy_info.port}")
                
            except Exception as e:
                logger.error(f"Failed to load proxy config {config}: {e}")
    
    def add_proxy(self, proxy_config: Dict[str, str]):
        """Add a single proxy to the pool"""
        try:
            proxy_info = ProxyInfo(**proxy_config)
            
            with self._lock:
                self.proxies.append(proxy_info)
                self.proxy_health[proxy_info.ip] = ProxyHealth(proxy=proxy_info)
            
            logger.info(f"Added proxy: {proxy_info.ip}:{proxy_info.port}")
            
        except Exception as e:
            logger.error(f"Failed to add proxy {proxy_config}: {e}")
    
    def remove_proxy(self, proxy_ip: str):
        """Remove proxy from pool"""
        with self._lock:
            self.proxies = [p for p in self.proxies if p.ip != proxy_ip]
            self.proxy_health.pop(proxy_ip, None)
        
        logger.info(f"Removed proxy: {proxy_ip}")
    
    def get_next_proxy(self) -> Optional[Dict[str, str]]:
        """
        Get next healthy proxy using round-robin with health weighting
        
        Returns:
            Proxy configuration dict or None if no healthy proxies
        """
        with self._lock:
            if not self.proxies:
                return None
            
            # Filter healthy proxies
            healthy_proxies = [
                p for p in self.proxies 
                if self.proxy_health[p.ip].is_healthy and 
                   self.proxy_health[p.ip].block_rate < self.block_rate_threshold
            ]
            
            if not healthy_proxies:
                # If no healthy proxies, use the best available
                logger.warning("No healthy proxies available, using best available")
                if self.proxies:
                    best_proxy = max(self.proxies, key=lambda p: self.proxy_health[p.ip].health_score)
                    return best_proxy.to_dict()
                return None
            
            # Use weighted selection based on health scores
            weights = [self.proxy_health[p.ip].health_score for p in healthy_proxies]
            
            # Adjust weights to favor less recently used proxies
            now = datetime.now(timezone.utc)
            for i, proxy in enumerate(healthy_proxies):
                health = self.proxy_health[proxy.ip]
                if health.last_check_time:
                    minutes_since_use = (now - health.last_check_time).total_seconds() / 60
                    if minutes_since_use > 30:  # Favor proxies not used in last 30 minutes
                        weights[i] *= 1.2
                
                # Reduce weight for heavily used proxies
                if health.total_requests > self.max_requests_per_proxy:
                    weights[i] *= 0.8
            
            # Select proxy based on weights
            selected_proxy = random.choices(healthy_proxies, weights=weights)[0]
            
            logger.debug(f"Selected proxy: {selected_proxy.ip} (score: {self.proxy_health[selected_proxy.ip].health_score:.2f})")
            
            return selected_proxy.to_dict()
    
    def get_proxy_by_country(self, country: str) -> Optional[Dict[str, str]]:
        """Get proxy from specific country"""
        with self._lock:
            country_proxies = [
                p for p in self.proxies 
                if p.country and p.country.lower() == country.lower() and
                   self.proxy_health[p.ip].is_healthy
            ]
            
            if not country_proxies:
                return None
            
            # Select best proxy from country
            best_proxy = max(country_proxies, key=lambda p: self.proxy_health[p.ip].health_score)
            return best_proxy.to_dict()
    
    def record_request_success(self, proxy_dict: Dict[str, str], response_time: float):
        """Record successful request for proxy"""
        proxy_ip = self._extract_proxy_ip(proxy_dict)
        
        if proxy_ip in self.proxy_health:
            with self._lock:
                self.proxy_health[proxy_ip].update_success(response_time)
                self.proxy_health[proxy_ip].last_check_time = datetime.now(timezone.utc)
    
    def record_request_failure(self, proxy_dict: Dict[str, str], error_type: str = "unknown"):
        """Record failed request for proxy"""
        proxy_ip = self._extract_proxy_ip(proxy_dict)
        
        if proxy_ip in self.proxy_health:
            with self._lock:
                self.proxy_health[proxy_ip].update_failure(error_type)
                self.proxy_health[proxy_ip].last_check_time = datetime.now(timezone.utc)
                
                # Auto-remove severely unhealthy proxies
                health = self.proxy_health[proxy_ip]
                if (health.consecutive_failures > 20 or 
                    health.block_rate > 0.8 or 
                    health.health_score < 0.1):
                    
                    logger.warning(f"Auto-removing unhealthy proxy: {proxy_ip}")
                    self.remove_proxy(proxy_ip)
    
    def _extract_proxy_ip(self, proxy_dict: Dict[str, str]) -> Optional[str]:
        """Extract IP from proxy dictionary"""
        proxy_url = proxy_dict.get('http', '')
        if not proxy_url:
            return None
        
        try:
            # Handle URLs with authentication
            if '@' in proxy_url:
                proxy_url = proxy_url.split('@')[1]
            
            # Remove protocol
            if '://' in proxy_url:
                proxy_url = proxy_url.split('://')[1]
            
            # Extract IP
            if ':' in proxy_url:
                return proxy_url.split(':')[0]
            
            return proxy_url
            
        except Exception:
            return None
    
    async def start_health_monitoring(self):
        """Start background health monitoring"""
        if self._health_check_running:
            return
        
        self._health_check_running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Started proxy health monitoring")
    
    async def stop_health_monitoring(self):
        """Stop background health monitoring"""
        if self._health_check_task:
            self._health_check_running = False
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Stopped proxy health monitoring")
    
    async def _health_check_loop(self):
        """Background health check loop"""
        while self._health_check_running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _perform_health_checks(self):
        """Perform health checks on all proxies"""
        if not self.proxies:
            return
        
        logger.debug("Performing proxy health checks")
        
        # Simple health check - test with httpbin or similar
        test_url = "http://httpbin.org/ip"
        timeout = 10
        
        for proxy in self.proxies[:]:  # Copy list to avoid modification during iteration
            try:
                health = self.proxy_health.get(proxy.ip)
                if not health:
                    continue
                
                # Skip recent checks
                if (health.last_check_time and 
                    (datetime.now(timezone.utc) - health.last_check_time).total_seconds() < 180):
                    continue
                
                # Perform check with aiohttp
                import aiohttp
                
                proxy_url = proxy.get_auth_url() if proxy.username else proxy.http_url
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                    start_time = time.time()
                    
                    async with session.get(test_url, proxy=proxy_url) as response:
                        response_time = time.time() - start_time
                        
                        if response.status == 200:
                            health.update_success(response_time)
                            logger.debug(f"Health check passed for {proxy.ip}")
                        else:
                            health.update_failure("health_check_failed")
                            logger.debug(f"Health check failed for {proxy.ip}: status {response.status}")
            
            except asyncio.TimeoutError:
                health.update_failure("timeout")
                logger.debug(f"Health check timeout for {proxy.ip}")
            
            except Exception as e:
                health.update_failure("connection_error")
                logger.debug(f"Health check error for {proxy.ip}: {e}")
            
            # Small delay between checks
            await asyncio.sleep(1)
    
    def get_proxy_statistics(self) -> Dict[str, Any]:
        """Get comprehensive proxy statistics"""
        with self._lock:
            total_proxies = len(self.proxies)
            healthy_proxies = sum(1 for h in self.proxy_health.values() if h.is_healthy)
            
            if not self.proxy_health:
                return {
                    'total_proxies': total_proxies,
                    'healthy_proxies': 0,
                    'average_health_score': 0.0,
                    'total_requests': 0,
                    'success_rate': 0.0
                }
            
            health_scores = [h.health_score for h in self.proxy_health.values()]
            total_requests = sum(h.total_requests for h in self.proxy_health.values())
            total_successes = sum(h.successful_requests for h in self.proxy_health.values())
            
            return {
                'total_proxies': total_proxies,
                'healthy_proxies': healthy_proxies,
                'unhealthy_proxies': total_proxies - healthy_proxies,
                'average_health_score': sum(health_scores) / len(health_scores) if health_scores else 0.0,
                'total_requests': total_requests,
                'total_successes': total_successes,
                'success_rate': total_successes / max(total_requests, 1),
                'proxy_details': {
                    ip: {
                        'health_score': health.health_score,
                        'success_rate': health.success_rate,
                        'total_requests': health.total_requests,
                        'consecutive_failures': health.consecutive_failures,
                        'block_rate': health.block_rate,
                        'is_healthy': health.is_healthy
                    }
                    for ip, health in self.proxy_health.items()
                }
            }
    
    def get_healthy_proxy_count(self) -> int:
        """Get count of healthy proxies"""
        with self._lock:
            return sum(1 for h in self.proxy_health.values() if h.is_healthy)
    
    def cleanup_unhealthy_proxies(self) -> int:
        """Remove all unhealthy proxies and return count removed"""
        removed_count = 0
        
        with self._lock:
            unhealthy_ips = [
                ip for ip, health in self.proxy_health.items() 
                if not health.is_healthy and health.consecutive_failures > 15
            ]
            
            for ip in unhealthy_ips:
                self.remove_proxy(ip)
                removed_count += 1
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} unhealthy proxies")
        
        return removed_count
    
    def __len__(self) -> int:
        """Return number of proxies"""
        return len(self.proxies)
    
    def __bool__(self) -> bool:
        """Return True if there are any proxies"""
        return len(self.proxies) > 0
