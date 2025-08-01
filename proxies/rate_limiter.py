"""
Rate Limiter for Amazon Scraper
Implements per-IP rate limiting with Redis backend
"""

import asyncio
import time
import logging
from typing import Dict, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import json
from urllib.parse import urlparse

import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded"""
    
    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    max_requests_per_ip: int = 5
    time_window_seconds: int = 60
    burst_allowance: int = 2  # Extra requests allowed for bursts
    backoff_multiplier: float = 1.5
    max_backoff_seconds: int = 300


class IPRateLimiter:
    """
    Redis-based rate limiter with per-IP tracking
    Uses sliding window algorithm for precise rate limiting
    """
    
    def __init__(self, config: RateLimitConfig, redis_url: str = "redis://localhost:6379/0"):
        """
        Initialize rate limiter
        
        Args:
            config: RateLimitConfig object
            redis_url: Redis connection URL
        """
        self.config = config
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        
        # Fallback in-memory storage for when Redis is unavailable
        self._memory_store: Dict[str, Dict[str, Any]] = {}
        self._use_redis = True
        
        logger.info(f"IPRateLimiter initialized with config: {config}")
    
    async def _get_redis_client(self) -> redis.Redis:
        """Get or create Redis client"""
        if self.redis_client is None:
            try:
                self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                await self.redis_client.ping()
                self._use_redis = True
                logger.info("Connected to Redis for rate limiting")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis, using in-memory storage: {e}")
                self._use_redis = False
                self.redis_client = None
        
        return self.redis_client
    
    async def is_allowed(self, ip: str) -> tuple[bool, Optional[int]]:
        """
        Check if request is allowed for IP
        
        Args:
            ip: IP address to check
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        now = time.time()
        window_start = now - self.config.time_window_seconds
        
        if self._use_redis:
            try:
                client = await self._get_redis_client()
                if client:
                    return await self._check_redis_limit(client, ip, now, window_start)
            except Exception as e:
                logger.warning(f"Redis rate limit check failed, falling back to memory: {e}")
                self._use_redis = False
        
        # Fallback to in-memory rate limiting
        return await self._check_memory_limit(ip, now, window_start)
    
    async def _check_redis_limit(self, client: redis.Redis, ip: str, now: float, window_start: float) -> tuple[bool, Optional[int]]:
        """Check rate limit using Redis"""
        key = f"rate_limit:{ip}"
        
        # Use Redis pipeline for atomic operations
        async with client.pipeline() as pipe:
            # Remove expired entries
            await pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current requests in window
            await pipe.zcard(key)
            
            # Get backoff info
            backoff_key = f"rate_limit_backoff:{ip}"
            await pipe.hgetall(backoff_key)
            
            results = await pipe.execute()
            
            current_count = results[1]
            backoff_info = results[2]
        
        # Check if in backoff period
        if backoff_info:
            backoff_until = float(backoff_info.get('until', 0))
            if now < backoff_until:
                retry_after = int(backoff_until - now) + 1
                logger.debug(f"IP {ip} in backoff period, retry after {retry_after}s")
                return False, retry_after
        
        # Check rate limit
        max_requests = self.config.max_requests_per_ip + self.config.burst_allowance
        
        if current_count >= max_requests:
            # Apply exponential backoff
            backoff_level = int(backoff_info.get('level', 0)) + 1
            backoff_seconds = min(
                self.config.backoff_multiplier ** backoff_level * 60,
                self.config.max_backoff_seconds
            )
            backoff_until = now + backoff_seconds
            
            # Store backoff info
            await client.hset(
                f"rate_limit_backoff:{ip}",
                mapping={
                    'level': backoff_level,
                    'until': backoff_until
                }
            )
            await client.expire(f"rate_limit_backoff:{ip}", int(backoff_seconds) + 60)
            
            logger.warning(f"Rate limit exceeded for IP {ip}, backoff for {backoff_seconds}s")
            return False, int(backoff_seconds)
        
        return True, None
    
    async def _check_memory_limit(self, ip: str, now: float, window_start: float) -> tuple[bool, Optional[int]]:
        """Check rate limit using in-memory storage"""
        if ip not in self._memory_store:
            self._memory_store[ip] = {
                'requests': [],
                'backoff_until': 0,
                'backoff_level': 0
            }
        
        ip_data = self._memory_store[ip]
        
        # Check backoff
        if now < ip_data['backoff_until']:
            retry_after = int(ip_data['backoff_until'] - now) + 1
            return False, retry_after
        
        # Clean old requests
        ip_data['requests'] = [req_time for req_time in ip_data['requests'] if req_time > window_start]
        
        # Check limit
        max_requests = self.config.max_requests_per_ip + self.config.burst_allowance
        
        if len(ip_data['requests']) >= max_requests:
            # Apply backoff
            ip_data['backoff_level'] += 1
            backoff_seconds = min(
                self.config.backoff_multiplier ** ip_data['backoff_level'] * 60,
                self.config.max_backoff_seconds
            )
            ip_data['backoff_until'] = now + backoff_seconds
            
            logger.warning(f"Memory rate limit exceeded for IP {ip}, backoff for {backoff_seconds}s")
            return False, int(backoff_seconds)
        
        return True, None
    
    async def record_request(self, ip: str):
        """
        Record a request for the IP
        
        Args:
            ip: IP address making the request
        """
        now = time.time()
        
        if self._use_redis:
            try:
                client = await self._get_redis_client()
                if client:
                    await self._record_redis_request(client, ip, now)
                    return
            except Exception as e:
                logger.warning(f"Failed to record request in Redis: {e}")
                self._use_redis = False
        
        # Fallback to memory
        await self._record_memory_request(ip, now)
    
    async def _record_redis_request(self, client: redis.Redis, ip: str, now: float):
        """Record request in Redis"""
        key = f"rate_limit:{ip}"
        
        # Add timestamp to sorted set
        await client.zadd(key, {str(now): now})
        
        # Set expiration
        await client.expire(key, self.config.time_window_seconds + 60)
        
        # Reset backoff on successful request
        backoff_key = f"rate_limit_backoff:{ip}"
        backoff_info = await client.hgetall(backoff_key)
        if backoff_info:
            # Reset backoff level if enough time has passed
            backoff_until = float(backoff_info.get('until', 0))
            if now > backoff_until + 300:  # 5 minutes grace period
                await client.delete(backoff_key)
    
    async def _record_memory_request(self, ip: str, now: float):
        """Record request in memory"""
        if ip not in self._memory_store:
            self._memory_store[ip] = {
                'requests': [],
                'backoff_until': 0,
                'backoff_level': 0
            }
        
        self._memory_store[ip]['requests'].append(now)
        
        # Reset backoff on successful request after grace period
        if (now > self._memory_store[ip]['backoff_until'] + 300 and 
            self._memory_store[ip]['backoff_level'] > 0):
            self._memory_store[ip]['backoff_level'] = max(0, self._memory_store[ip]['backoff_level'] - 1)
    
    async def wait_if_needed(self, ip: str):
        """
        Wait if rate limit would be exceeded
        
        Args:
            ip: IP address to check
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded and waiting would be too long
        """
        allowed, retry_after = await self.is_allowed(ip)
        
        if not allowed:
            if retry_after and retry_after > self.config.max_backoff_seconds:
                raise RateLimitExceeded(
                    f"Rate limit exceeded for IP {ip}, retry after {retry_after}s",
                    retry_after=retry_after
                )
            
            if retry_after:
                logger.info(f"Rate limiting IP {ip}, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
        
        await self.record_request(ip)
    
    async def get_rate_limit_info(self, ip: str) -> Dict[str, Any]:
        """
        Get rate limit information for an IP
        
        Args:
            ip: IP address to check
            
        Returns:
            Dictionary with rate limit info
        """
        now = time.time()
        window_start = now - self.config.time_window_seconds
        
        info = {
            'ip': ip,
            'max_requests': self.config.max_requests_per_ip,
            'window_seconds': self.config.time_window_seconds,
            'current_requests': 0,
            'requests_remaining': self.config.max_requests_per_ip,
            'reset_time': now + self.config.time_window_seconds,
            'is_allowed': True,
            'backoff_until': None,
            'backoff_level': 0
        }
        
        if self._use_redis:
            try:
                client = await self._get_redis_client()
                if client:
                    # Get current count
                    key = f"rate_limit:{ip}"
                    await client.zremrangebyscore(key, 0, window_start)
                    current_count = await client.zcard(key)
                    info['current_requests'] = current_count
                    
                    # Get backoff info
                    backoff_key = f"rate_limit_backoff:{ip}"
                    backoff_info = await client.hgetall(backoff_key)
                    if backoff_info:
                        info['backoff_until'] = float(backoff_info.get('until', 0))
                        info['backoff_level'] = int(backoff_info.get('level', 0))
                        info['is_allowed'] = now >= info['backoff_until']
                    
                    info['requests_remaining'] = max(0, self.config.max_requests_per_ip - current_count)
                    return info
            except Exception as e:
                logger.warning(f"Failed to get rate limit info from Redis: {e}")
        
        # Fallback to memory
        if ip in self._memory_store:
            ip_data = self._memory_store[ip]
            # Clean old requests
            ip_data['requests'] = [req_time for req_time in ip_data['requests'] if req_time > window_start]
            
            info['current_requests'] = len(ip_data['requests'])
            info['requests_remaining'] = max(0, self.config.max_requests_per_ip - len(ip_data['requests']))
            info['backoff_until'] = ip_data['backoff_until']
            info['backoff_level'] = ip_data['backoff_level']
            info['is_allowed'] = now >= ip_data['backoff_until']
        
        return info
    
    async def reset_ip_limit(self, ip: str):
        """
        Reset rate limit for a specific IP
        
        Args:
            ip: IP address to reset
        """
        if self._use_redis:
            try:
                client = await self._get_redis_client()
                if client:
                    await client.delete(f"rate_limit:{ip}")
                    await client.delete(f"rate_limit_backoff:{ip}")
                    logger.info(f"Reset rate limit for IP {ip} in Redis")
                    return
            except Exception as e:
                logger.warning(f"Failed to reset rate limit in Redis: {e}")
        
        # Reset in memory
        if ip in self._memory_store:
            del self._memory_store[ip]
            logger.info(f"Reset rate limit for IP {ip} in memory")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get rate limiter statistics"""
        stats = {
            'using_redis': self._use_redis,
            'config': {
                'max_requests_per_ip': self.config.max_requests_per_ip,
                'time_window_seconds': self.config.time_window_seconds,
                'burst_allowance': self.config.burst_allowance,
                'max_backoff_seconds': self.config.max_backoff_seconds
            },
            'tracked_ips': 0,
            'total_requests': 0,
            'ips_in_backoff': 0
        }
        
        if self._use_redis:
            try:
                client = await self._get_redis_client()
                if client:
                    # Get all rate limit keys
                    keys = await client.keys("rate_limit:*")
                    stats['tracked_ips'] = len([k for k in keys if not k.endswith('_backoff')])
                    
                    # Count backoff keys
                    backoff_keys = await client.keys("rate_limit_backoff:*")
                    stats['ips_in_backoff'] = len(backoff_keys)
                    
                    return stats
            except Exception as e:
                logger.warning(f"Failed to get Redis statistics: {e}")
        
        # Memory statistics
        stats['tracked_ips'] = len(self._memory_store)
        now = time.time()
        stats['ips_in_backoff'] = sum(1 for ip_data in self._memory_store.values() if ip_data['backoff_until'] > now)
        stats['total_requests'] = sum(len(ip_data['requests']) for ip_data in self._memory_store.values())
        
        return stats
    
    async def cleanup_expired_data(self):
        """Clean up expired data from memory storage"""
        if self._use_redis:
            return  # Redis handles expiration automatically
        
        now = time.time()
        window_start = now - self.config.time_window_seconds
        
        # Clean up expired data
        for ip, ip_data in list(self._memory_store.items()):
            # Remove old requests
            ip_data['requests'] = [req_time for req_time in ip_data['requests'] if req_time > window_start]
            
            # Remove IPs with no recent activity and not in backoff
            if not ip_data['requests'] and ip_data['backoff_until'] <= now:
                del self._memory_store[ip]
        
        logger.debug(f"Cleaned up expired rate limit data, tracking {len(self._memory_store)} IPs")
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            logger.info("Closed Redis connection")


class RateLimitedRequester:
    """
    Wrapper that automatically handles rate limiting for requests
    """
    
    def __init__(self, rate_limiter: IPRateLimiter):
        """
        Initialize rate limited requester
        
        Args:
            rate_limiter: IPRateLimiter instance
        """
        self.rate_limiter = rate_limiter
    
    async def request(self, ip: str, request_func, *args, **kwargs):
        """
        Make a rate-limited request
        
        Args:
            ip: IP address making the request
            request_func: Async function to call for the request
            *args, **kwargs: Arguments for request_func
            
        Returns:
            Result of request_func
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        await self.rate_limiter.wait_if_needed(ip)
        
        try:
            result = await request_func(*args, **kwargs)
            logger.debug(f"Rate-limited request succeeded for IP {ip}")
            return result
        except Exception as e:
            logger.error(f"Rate-limited request failed for IP {ip}: {e}")
            raise


def extract_ip_from_proxy(proxy_config: Dict[str, str]) -> Optional[str]:
    """
    Extract IP address from proxy configuration
    
    Args:
        proxy_config: Proxy configuration dictionary
        
    Returns:
        IP address or None if extraction fails
    """
    proxy_url = proxy_config.get('http', '') or proxy_config.get('https', '')
    
    if not proxy_url:
        return None
    
    try:
        # Handle authentication in URL
        if '@' in proxy_url:
            proxy_url = proxy_url.split('@')[1]
        
        # Parse URL
        parsed = urlparse(f"http://{proxy_url}" if '://' not in proxy_url else proxy_url)
        return parsed.hostname
        
    except Exception:
        logger.warning(f"Failed to extract IP from proxy config: {proxy_config}")
        return None


def create_default_rate_limiter(redis_url: str = "redis://localhost:6379/0") -> IPRateLimiter:
    """
    Create a rate limiter with default configuration
    
    Args:
        redis_url: Redis connection URL
        
    Returns:
        Configured IPRateLimiter instance
    """
    config = RateLimitConfig(
        max_requests_per_ip=5,
        time_window_seconds=60,
        burst_allowance=2,
        backoff_multiplier=1.5,
        max_backoff_seconds=300
    )
    
    return IPRateLimiter(config, redis_url)
