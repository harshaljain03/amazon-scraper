"""
HTTP Fetcher for Amazon Scraper
Provides synchronous and asynchronous HTTP fetching with error handling
"""

import time
import logging
import asyncio
from typing import Dict, Optional, Any, Union
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from proxies.rate_limiter import RateLimitExceeded

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of an HTTP fetch operation"""
    success: bool
    status_code: Optional[int]
    html: str
    headers: Dict[str, str]
    url: str
    response_time: float
    error: Optional[str] = None


class HTTPFetchError(Exception):
    """Custom exception for HTTP fetch errors"""
    
    def __init__(self, message: str, status_code: Optional[int] = None, url: str = ""):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.url = url
    
    def __str__(self):
        return f"HTTPFetchError: {self.message} (URL: {self.url}, Status: {self.status_code})"


class HTTPFetcher:
    """
    Synchronous HTTP fetcher with retry logic and error handling
    """
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        Initialize HTTP fetcher
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Create session with default headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        logger.info("HTTPFetcher initialized with timeout=%d, max_retries=%d", timeout, max_retries)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((requests.RequestException, HTTPFetchError))
    )
    def fetch(self, url: str, headers: Optional[Dict[str, str]] = None) -> FetchResult:
        """
        Fetch a URL with retry logic
        
        Args:
            url: URL to fetch
            headers: Additional headers to send
            
        Returns:
            FetchResult with response data
            
        Raises:
            HTTPFetchError: On fetch failure
            RateLimitExceeded: When rate limit is exceeded
        """
        start_time = time.time()
        
        try:
            # Merge headers
            request_headers = self.session.headers.copy()
            if headers:
                request_headers.update(headers)
            
            logger.debug("Fetching URL: %s", url)
            
            response = self.session.get(
                url,
                headers=request_headers,
                timeout=self.timeout,
                allow_redirects=True,
                verify=True
            )
            
            response_time = time.time() - start_time
            
            # Check for rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', '60')
                raise RateLimitExceeded(f"Rate limit exceeded for {url}", retry_after=int(retry_after))
            
            # Check for other HTTP errors
            if response.status_code >= 400:
                raise HTTPFetchError(
                    f"HTTP {response.status_code}: {response.reason}",
                    status_code=response.status_code,
                    url=url
                )
            
            logger.info("Successfully fetched %s (status=%d, time=%.2fs)", 
                       url, response.status_code, response_time)
            
            return FetchResult(
                success=True,
                status_code=response.status_code,
                html=response.text,
                headers=dict(response.headers),
                url=response.url,
                response_time=response_time
            )
            
        except requests.exceptions.Timeout:
            error_msg = f"Request timeout after {self.timeout}s"
            logger.error("%s for URL: %s", error_msg, url)
            raise HTTPFetchError(error_msg, url=url)
        
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error: {str(e)}"
            logger.error("%s for URL: %s", error_msg, url)
            raise HTTPFetchError(error_msg, url=url)
        
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error("%s for URL: %s", error_msg, url)
            raise HTTPFetchError(error_msg, url=url)
        
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error("%s for URL: %s", error_msg, url, exc_info=True)
            raise HTTPFetchError(error_msg, url=url)
    
    def fetch_with_proxy(self, url: str, proxy: Dict[str, str], 
                        headers: Optional[Dict[str, str]] = None) -> FetchResult:
        """
        Fetch URL using a specific proxy
        
        Args:
            url: URL to fetch
            proxy: Proxy configuration dict
            headers: Additional headers
            
        Returns:
            FetchResult with response data
        """
        original_proxies = self.session.proxies.copy()
        
        try:
            # Set proxy for this request
            self.session.proxies.update(proxy)
            
            logger.debug("Fetching %s via proxy %s", url, proxy.get('http', 'N/A'))
            
            return self.fetch(url, headers)
            
        finally:
            # Restore original proxy settings
            self.session.proxies = original_proxies
    
    def close(self):
        """Close the HTTP session"""
        self.session.close()
        logger.info("HTTPFetcher session closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AsyncHTTPFetcher:
    """
    Asynchronous HTTP fetcher with retry logic and error handling
    """
    
    def __init__(self, timeout: int = 30, max_retries: int = 3, 
                 connector_limit: int = 100):
        """
        Initialize async HTTP fetcher
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            connector_limit: Maximum number of connections
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.connector_limit = connector_limit
        
        # Default headers
        self.default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        self.session: Optional[aiohttp.ClientSession] = None
        logger.info("AsyncHTTPFetcher initialized")
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def initialize(self):
        """Initialize the aiohttp session"""
        if self.session is None:
            connector = aiohttp.TCPConnector(
                limit=self.connector_limit,
                limit_per_host=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self.default_headers
            )
            
            logger.info("AsyncHTTPFetcher session initialized")
    
    async def fetch(self, url: str, headers: Optional[Dict[str, str]] = None) -> FetchResult:
        """
        Async fetch a URL with retry logic
        
        Args:
            url: URL to fetch
            headers: Additional headers to send
            
        Returns:
            FetchResult with response data
        """
        if self.session is None:
            await self.initialize()
        
        start_time = time.time()
        
        for attempt in range(self.max_retries):
            try:
                # Merge headers
                request_headers = self.default_headers.copy()
                if headers:
                    request_headers.update(headers)
                
                logger.debug("Async fetching URL: %s (attempt %d)", url, attempt + 1)
                
                async with self.session.get(url, headers=request_headers) as response:
                    response_time = time.time() - start_time
                    
                    # Check for rate limiting
                    if response.status == 429:
                        retry_after = response.headers.get('Retry-After', '60')
                        raise RateLimitExceeded(f"Rate limit exceeded for {url}", retry_after=int(retry_after))
                    
                    # Check for other HTTP errors
                    if response.status >= 400:
                        raise HTTPFetchError(
                            f"HTTP {response.status}: {response.reason}",
                            status_code=response.status,
                            url=url
                        )
                    
                    html = await response.text()
                    
                    logger.info("Successfully fetched %s (status=%d, time=%.2fs)", 
                               url, response.status, response_time)
                    
                    return FetchResult(
                        success=True,
                        status_code=response.status,
                        html=html,
                        headers=dict(response.headers),
                        url=str(response.url),
                        response_time=response_time
                    )
            
            except asyncio.TimeoutError:
                error_msg = f"Request timeout after {self.timeout}s"
                logger.warning("%s for URL: %s (attempt %d)", error_msg, url, attempt + 1)
                
                if attempt == self.max_retries - 1:
                    raise HTTPFetchError(error_msg, url=url)
                
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            except aiohttp.ClientError as e:
                error_msg = f"Client error: {str(e)}"
                logger.warning("%s for URL: %s (attempt %d)", error_msg, url, attempt + 1)
                
                if attempt == self.max_retries - 1:
                    raise HTTPFetchError(error_msg, url=url)
                
                await asyncio.sleep(2 ** attempt)
            
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error("%s for URL: %s (attempt %d)", error_msg, url, attempt + 1, exc_info=True)
                
                if attempt == self.max_retries - 1:
                    raise HTTPFetchError(error_msg, url=url)
                
                await asyncio.sleep(2 ** attempt)
        
        # Should never reach here due to the raise statements above
        raise HTTPFetchError(f"Failed to fetch {url} after {self.max_retries} attempts", url=url)
    
    async def fetch_with_proxy(self, url: str, proxy: str, 
                              headers: Optional[Dict[str, str]] = None) -> FetchResult:
        """
        Async fetch URL using a specific proxy
        
        Args:
            url: URL to fetch
            proxy: Proxy URL
            headers: Additional headers
            
        Returns:
            FetchResult with response data
        """
        if self.session is None:
            await self.initialize()
        
        # Create a new session with proxy for this request
        connector = aiohttp.TCPConnector(limit=10)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.default_headers
        ) as proxy_session:
            
            start_time = time.time()
            
            try:
                request_headers = self.default_headers.copy()
                if headers:
                    request_headers.update(headers)
                
                logger.debug("Async fetching %s via proxy %s", url, proxy)
                
                async with proxy_session.get(url, headers=request_headers, proxy=proxy) as response:
                    response_time = time.time() - start_time
                    
                    if response.status >= 400:
                        raise HTTPFetchError(
                            f"HTTP {response.status}: {response.reason}",
                            status_code=response.status,
                            url=url
                        )
                    
                    html = await response.text()
                    
                    logger.info("Successfully fetched %s via proxy (status=%d, time=%.2fs)", 
                               url, response.status, response_time)
                    
                    return FetchResult(
                        success=True,
                        status_code=response.status,
                        html=html,
                        headers=dict(response.headers),
                        url=str(response.url),
                        response_time=response_time
                    )
            
            except Exception as e:
                error_msg = f"Proxy fetch failed: {str(e)}"
                logger.error("%s for URL: %s", error_msg, url)
                raise HTTPFetchError(error_msg, url=url)
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("AsyncHTTPFetcher session closed")
