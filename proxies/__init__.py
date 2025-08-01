"""
Proxy Management Module for Amazon Scraper
Handles proxy rotation, health monitoring, and rate limiting
"""

from .proxy_manager import ProxyManager, ProxyInfo, ProxyHealth
from .rate_limiter import (
    IPRateLimiter, 
    RateLimitConfig, 
    RateLimitExceeded, 
    RateLimitedRequester,
    create_default_rate_limiter,
    extract_ip_from_proxy
)

__all__ = [
    'ProxyManager',
    'ProxyInfo', 
    'ProxyHealth',
    'IPRateLimiter',
    'RateLimitConfig',
    'RateLimitExceeded',
    'RateLimitedRequester', 
    'create_default_rate_limiter',
    'extract_ip_from_proxy',
]
