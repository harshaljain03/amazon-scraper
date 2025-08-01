"""
Playwright-based HTTP Fetcher for Amazon Scraper
Provides JavaScript rendering, proxy support, and anti-detection features
"""

import asyncio
import logging
import time
import random
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright._impl._api_types import Error as PlaywrightError

from crawler.http_fetcher import FetchResult, HTTPFetchError
from proxies.rate_limiter import IPRateLimiter, RateLimitedRequester, RateLimitExceeded, extract_ip_from_proxy

logger = logging.getLogger(__name__)


@dataclass
class PlaywrightConfig:
    """Configuration for Playwright fetcher"""
    headless: bool = True
    timeout: int = 30000  # Playwright uses milliseconds
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str = None
    accept_downloads: bool = False
    ignore_https_errors: bool = True
    javascript_enabled: bool = True
    wait_for_network_idle: bool = True
    network_idle_timeout: int = 500
    extra_http_headers: Dict[str, str] = None
    locale: str = "en-US"
    timezone: str = "America/New_York"


class PlaywrightFetcher:
    """
    Playwright-based fetcher with JavaScript rendering and anti-detection
    """
    
    def __init__(self, 
                 config: PlaywrightConfig = None,
                 rate_limiter: IPRateLimiter = None,
                 browser_type: str = "chromium"):
        """
        Initialize Playwright fetcher
        
        Args:
            config: PlaywrightConfig object
            rate_limiter: Optional rate limiter
            browser_type: Browser type ('chromium', 'firefox', 'webkit')
        """
        self.config = config or PlaywrightConfig()
        self.rate_limiter = rate_limiter
        self.browser_type = browser_type
        
        # Set default user agent if not provided
        if not self.config.user_agent:
            self.config.user_agent = self._get_random_user_agent()
        
        # Playwright objects
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        
        # Track if initialized
        self._initialized = False
        
        logger.info(f"Playwright fetcher initialized with {browser_type} browser")
    
    def _get_random_user_agent(self) -> str:
        """Get a random realistic user agent"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0"
        ]
        return random.choice(user_agents)
    
    async def initialize(self):
        """Initialize Playwright browser and context"""
        if self._initialized:
            return
        
        try:
            self.playwright = await async_playwright().start()
            
            # Get browser launcher
            if self.browser_type == "chromium":
                browser_launcher = self.playwright.chromium
            elif self.browser_type == "firefox":
                browser_launcher = self.playwright.firefox
            elif self.browser_type == "webkit":
                browser_launcher = self.playwright.webkit
            else:
                raise ValueError(f"Unsupported browser type: {self.browser_type}")
            
            # Launch browser with anti-detection features
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--disable-extensions",
                "--no-first-run",
                "--disable-default-apps",
                "--disable-background-networking",
            ]
            
            self.browser = await browser_launcher.launch(
                headless=self.config.headless,
                args=launch_args
            )
            
            # Create context with stealth settings
            context_options = {
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height
                },
                "user_agent": self.config.user_agent,
                "locale": self.config.locale,
                "timezone_id": self.config.timezone,
                "ignore_https_errors": self.config.ignore_https_errors,
                "java_script_enabled": self.config.javascript_enabled,
                "accept_downloads": self.config.accept_downloads,
            }
            
            if self.config.extra_http_headers:
                context_options["extra_http_headers"] = self.config.extra_http_headers
            
            self.context = await self.browser.new_context(**context_options)
            
            # Add stealth scripts to avoid detection
            await self.context.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                });
                
                // Mock plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                // Mock languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                // Mock permissions
                const originalQuery = window.navigator.permissions.query;
                return window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Mock chrome runtime
                window.chrome = {
                    runtime: {},
                };
                
                // Override the `plugins` property to use a custom getter
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        return [
                            {
                                0: {
                                    type: "application/x-google-chrome-pdf",
                                    suffixes: "pdf",
                                    description: "Portable Document Format",
                                    enabledPlugin: Plugin,
                                },
                                description: "Portable Document Format",
                                filename: "internal-pdf-viewer",
                                length: 1,
                                name: "Chrome PDF Plugin",
                            },
                            {
                                0: {
                                    type: "application/pdf",
                                    suffixes: "pdf", 
                                    description: "",
                                    enabledPlugin: Plugin,
                                },
                                description: "",
                                filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                                length: 1,
                                name: "Chrome PDF Viewer",
                            },
                            {
                                0: {
                                    type: "application/x-nacl",
                                    suffixes: "",
                                    description: "Native Client Executable",
                                    enabledPlugin: Plugin,
                                },
                                1: {
                                    type: "application/x-pnacl",
                                    suffixes: "",
                                    description: "Portable Native Client Executable",
                                    enabledPlugin: Plugin,
                                },
                                description: "",
                                filename: "internal-nacl-plugin",
                                length: 2,
                                name: "Native Client",
                            },
                        ];
                    },
                });
            """)
            
            self._initialized = True
            logger.info("Playwright browser and context initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Playwright: {e}")
            await self.cleanup()
            raise
    
    async def fetch(self, url: str, proxy: Dict[str, str] = None, **kwargs) -> FetchResult:
        """
        Fetch a URL using Playwright
        
        Args:
            url: URL to fetch
            proxy: Optional proxy configuration
            **kwargs: Additional options
            
        Returns:
            FetchResult with page content
        """
        if not self._initialized:
            await self.initialize()
        
        # Apply rate limiting if configured
        if self.rate_limiter and proxy:
            proxy_ip = extract_ip_from_proxy(proxy)
            if proxy_ip:
                await self.rate_limiter.wait_if_needed(proxy_ip)
        
        start_time = time.time()
        page = None
        
        try:
            # Create new page
            page = await self.context.new_page()
            
            # Set proxy if provided
            if proxy:
                await page.route("**/*", lambda route: route.continue_(proxy=proxy))
            
            # Navigate to URL
            logger.debug(f"Navigating to: {url}")
            
            response = await page.goto(
                url,
                timeout=self.config.timeout,
                wait_until="domcontentloaded"
            )
            
            # Wait for network idle if configured
            if self.config.wait_for_network_idle:
                try:
                    await page.wait_for_load_state("networkidle", timeout=self.config.network_idle_timeout)
                except PlaywrightTimeoutError:
                    logger.debug("Network idle timeout, continuing...")
            
            # Get page content
            html = await page.content()
            response_time = time.time() - start_time
            
            # Get final URL (after redirects)
            final_url = page.url
            
            # Get response headers
            headers = {}
            if response:
                headers = await response.all_headers()
            
            logger.info(f"Successfully fetched {url} (time={response_time:.2f}s)")
            
            return FetchResult(
                success=True,
                status_code=response.status if response else 200,
                html=html,
                headers=headers,
                url=final_url,
                response_time=response_time
            )
            
        except PlaywrightTimeoutError:
            error_msg = f"Page timeout after {self.config.timeout}ms"
            logger.error(f"{error_msg} for URL: {url}")
            raise HTTPFetchError(error_msg, url=url)
        
        except PlaywrightError as e:
            error_msg = f"Playwright error: {str(e)}"
            logger.error(f"{error_msg} for URL: {url}")
            raise HTTPFetchError(error_msg, url=url)
        
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"{error_msg} for URL: {url}", exc_info=True)
            raise HTTPFetchError(error_msg, url=url)
        
        finally:
            if page:
                await page.close()
    
    async def fetch_with_proxy(self, url: str, proxy: Dict[str, str], **kwargs) -> FetchResult:
        """
        Fetch URL with specific proxy (convenience method)
        
        Args:
            url: URL to fetch
            proxy: Proxy configuration
            **kwargs: Additional options
            
        Returns:
            FetchResult with page content
        """
        return await self.fetch(url, proxy=proxy, **kwargs)
    
    async def cleanup(self):
        """Clean up Playwright resources"""
        try:
            if self.context:
                await self.context.close()
                self.context = None
            
            if self.browser:
                await self.browser.close()
                self.browser = None
            
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            
            self._initialized = False
            logger.info("Playwright resources cleaned up")
            
        except Exception as e:
            logger.error(f"Error during Playwright cleanup: {e}")
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()


def create_stealth_config() -> PlaywrightConfig:
    """Create a stealth-optimized Playwright configuration"""
    return PlaywrightConfig(
        headless=True,
        timeout=30000,
        viewport_width=1920,
        viewport_height=1080,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ignore_https_errors=True,
        javascript_enabled=True,
        wait_for_network_idle=True,
        network_idle_timeout=1000,
        locale="en-US",
        timezone="America/New_York",
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
            "DNT": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
    )
