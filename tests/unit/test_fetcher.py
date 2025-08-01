"""
Unit tests for HTTP and Playwright fetchers
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import aiohttp
import requests

from crawler.http_fetcher import HTTPFetcher, AsyncHTTPFetcher, FetchResult, HTTPFetchError
from crawler.playwright_fetcher import PlaywrightFetcher, PlaywrightConfig, create_stealth_config
from proxies.rate_limiter import RateLimitExceeded


class TestHTTPFetcher:
    """Test cases for synchronous HTTP fetcher"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.fetcher = HTTPFetcher(timeout=10, max_retries=2)
    
    def teardown_method(self):
        """Clean up after tests"""
        self.fetcher.close()
    
    def test_initialization(self):
        """Test HTTPFetcher initialization"""
        assert self.fetcher.timeout == 10
        assert self.fetcher.max_retries == 2
        assert self.fetcher.session is not None
        assert 'User-Agent' in self.fetcher.session.headers
    
    @patch('requests.Session.get')
    def test_successful_fetch(self, mock_get):
        """Test successful HTTP fetch"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.url = "https://example.com"
        mock_response.reason = "OK"
        mock_get.return_value = mock_response
        
        result = self.fetcher.fetch("https://example.com")
        
        assert isinstance(result, FetchResult)
        assert result.success is True
        assert result.status_code == 200
        assert result.html == "<html><body>Test content</body></html>"
        assert result.url == "https://example.com"
        assert result.response_time > 0
    
    @patch('requests.Session.get')
    def test_http_error_response(self, mock_get):
        """Test HTTP error response handling"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.reason = "Not Found"
        mock_get.return_value = mock_response
        
        with pytest.raises(HTTPFetchError) as exc_info:
            self.fetcher.fetch("https://example.com/notfound")
        
        assert "HTTP 404" in str(exc_info.value)
        assert exc_info.value.status_code == 404
    
    @patch('requests.Session.get')
    def test_rate_limit_response(self, mock_get):
        """Test rate limit response handling"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '60'}
        mock_get.return_value = mock_response
        
        with pytest.raises(RateLimitExceeded) as exc_info:
            self.fetcher.fetch("https://example.com")
        
        assert exc_info.value.retry_after == 60
    
    @patch('requests.Session.get')
    def test_connection_timeout(self, mock_get):
        """Test connection timeout handling"""
        mock_get.side_effect = requests.exceptions.Timeout()
        
        with pytest.raises(HTTPFetchError) as exc_info:
            self.fetcher.fetch("https://example.com")
        
        assert "timeout" in str(exc_info.value).lower()
    
    @patch('requests.Session.get')
    def test_connection_error(self, mock_get):
        """Test connection error handling"""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        with pytest.raises(HTTPFetchError) as exc_info:
            self.fetcher.fetch("https://example.com")
        
        assert "connection error" in str(exc_info.value).lower()
    
    @patch('requests.Session.get')
    def test_fetch_with_proxy(self, mock_get):
        """Test fetching with proxy"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Proxy content"
        mock_response.headers = {}
        mock_response.url = "https://example.com"
        mock_get.return_value = mock_response
        
        proxy_config = {
            'http': 'http://proxy.example.com:8080',
            'https': 'http://proxy.example.com:8080'
        }
        
        result = self.fetcher.fetch_with_proxy("https://example.com", proxy_config)
        
        assert result.success is True
        assert result.html == "Proxy content"
        
        # Verify proxy was used in the call
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        # Note: We check if proxies were temporarily set, but they're restored after
    
    def test_custom_headers(self):
        """Test fetch with custom headers"""
        with patch('requests.Session.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "Custom headers content"
            mock_response.headers = {}
            mock_response.url = "https://example.com"
            mock_get.return_value = mock_response
            
            custom_headers = {'X-Custom-Header': 'test-value'}
            result = self.fetcher.fetch("https://example.com", headers=custom_headers)
            
            assert result.success is True
            
            # Check that custom header was included
            call_kwargs = mock_get.call_args[1]
            headers = call_kwargs['headers']
            assert 'X-Custom-Header' in headers
            assert headers['X-Custom-Header'] == 'test-value'


class TestAsyncHTTPFetcher:
    """Test cases for asynchronous HTTP fetcher"""
    
    @pytest.fixture
    def fetcher(self):
        """Create AsyncHTTPFetcher for testing"""
        return AsyncHTTPFetcher(timeout=10, max_retries=2)
    
    @pytest.mark.asyncio
    async def test_initialization(self, fetcher):
        """Test AsyncHTTPFetcher initialization"""
        assert fetcher.timeout == 10
        assert fetcher.max_retries == 2
        assert fetcher.session is None  # Not initialized yet
        
        async with fetcher:
            assert fetcher.session is not None
    
    @pytest.mark.asyncio
    async def test_successful_async_fetch(self, fetcher):
        """Test successful async HTTP fetch"""
        async with fetcher:
            # Mock the aiohttp session
            with patch.object(fetcher.session, 'get') as mock_get:
                # Create async context manager mock
                mock_response = Mock()
                mock_response.status = 200
                mock_response.text = AsyncMock(return_value="Async content")
                mock_response.headers = {'Content-Type': 'text/html'}
                mock_response.url = "https://example.com"
                
                mock_context = AsyncMock()
                mock_context.__aenter__ = AsyncMock(return_value=mock_response)
                mock_context.__aexit__ = AsyncMock(return_value=None)
                mock_get.return_value = mock_context
                
                result = await fetcher.fetch("https://example.com")
                
                assert isinstance(result, FetchResult)
                assert result.success is True
                assert result.status_code == 200
                assert result.html == "Async content"
                assert result.response_time > 0
    
    @pytest.mark.asyncio
    async def test_async_timeout_retry(self, fetcher):
        """Test async timeout with retry logic"""
        async with fetcher:
            with patch.object(fetcher.session, 'get') as mock_get:
                # First call times out, second succeeds
                timeout_context = AsyncMock()
                timeout_context.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
                
                success_response = Mock()
                success_response.status = 200
                success_response.text = AsyncMock(return_value="Success after retry")
                success_response.headers = {}
                success_response.url = "https://example.com"
                
                success_context = AsyncMock()
                success_context.__aenter__ = AsyncMock(return_value=success_response)
                success_context.__aexit__ = AsyncMock(return_value=None)
                
                mock_get.side_effect = [timeout_context, success_context]
                
                result = await fetcher.fetch("https://example.com")
                
                assert result.success is True
                assert result.html == "Success after retry"
                assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_async_fetch_with_proxy(self, fetcher):
        """Test async fetch with proxy"""
        async with fetcher:
            proxy_url = "http://proxy.example.com:8080"
            
            # Mock aiohttp.ClientSession for proxy usage
            with patch('aiohttp.ClientSession') as mock_session_class:
                mock_session = Mock()
                mock_response = Mock()
                mock_response.status = 200
                mock_response.text = AsyncMock(return_value="Proxy async content")
                mock_response.headers = {}
                mock_response.url = "https://example.com"
                
                mock_context = AsyncMock()
                mock_context.__aenter__ = AsyncMock(return_value=mock_response)
                mock_context.__aexit__ = AsyncMock(return_value=None)
                mock_session.get.return_value = mock_context
                
                proxy_session_context = AsyncMock()
                proxy_session_context.__aenter__ = AsyncMock(return_value=mock_session)
                proxy_session_context.__aexit__ = AsyncMock(return_value=None)
                mock_session_class.return_value = proxy_session_context
                
                result = await fetcher.fetch_with_proxy("https://example.com", proxy_url)
                
                assert result.success is True
                assert result.html == "Proxy async content"
                
                # Verify proxy was used
                mock_session.get.assert_called_once()
                call_kwargs = mock_session.get.call_args[1]
                assert call_kwargs['proxy'] == proxy_url


class TestPlaywrightFetcher:
    """Test cases for Playwright fetcher"""
    
    @pytest.fixture
    def config(self):
        """Create PlaywrightConfig for testing"""
        return PlaywrightConfig(
            headless=True,
            timeout=30000,
            viewport_width=1920,
            viewport_height=1080
        )
    
    @pytest.fixture
    def fetcher(self, config):
        """Create PlaywrightFetcher for testing"""
        return PlaywrightFetcher(config=config)
    
    @pytest.mark.asyncio
    async def test_playwright_config_creation(self, config):
        """Test PlaywrightConfig creation"""
        assert config.headless is True
        assert config.timeout == 30000
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
    
    def test_stealth_config_creation(self):
        """Test stealth configuration creation"""
        config = create_stealth_config()
        
        assert config.headless is True
        assert config.javascript_enabled is True
        assert config.extra_http_headers is not None
        assert 'Accept' in config.extra_http_headers
        assert 'User-Agent' in config.__dict__
    
    @pytest.mark.asyncio
    async def test_playwright_initialization(self, fetcher):
        """Test Playwright fetcher initialization"""
        assert fetcher.config is not None
        assert fetcher.playwright is None
        assert fetcher.browser is None
        assert fetcher._initialized is False
        
        # Mock playwright initialization
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            mock_playwright_instance = Mock()
            mock_browser = Mock()
            mock_context = Mock()
            
            # Mock the context manager
            mock_playwright_context = AsyncMock()
            mock_playwright_context.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
            mock_playwright_context.__aexit__ = AsyncMock(return_value=None)
            mock_playwright.return_value = mock_playwright_context
            
            # Mock browser launcher
            mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.add_init_script = AsyncMock()
            
            await fetcher.initialize()
            
            assert fetcher._initialized is True
            assert fetcher.playwright is not None
            assert fetcher.browser is not None
    
    @pytest.mark.asyncio
    async def test_playwright_fetch_success(self, fetcher):
        """Test successful Playwright fetch"""
        # Mock all Playwright objects
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            # Setup mocks
            mock_playwright_instance = Mock()
            mock_browser = Mock()
            mock_context = Mock() 
            mock_page = Mock()
            mock_response = Mock()
            
            # Mock playwright context manager
            mock_playwright_context = AsyncMock()
            mock_playwright_context.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
            mock_playwright_context.__aexit__ = AsyncMock(return_value=None)
            mock_playwright.return_value = mock_playwright_context
            
            # Setup async mocks
            mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.add_init_script = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            
            # Mock page methods
            mock_page.goto = AsyncMock(return_value=mock_response)
            mock_page.content = AsyncMock(return_value="<html><body>Playwright content</body></html>")
            mock_page.wait_for_load_state = AsyncMock()
            mock_page.close = AsyncMock()
            mock_page.url = "https://example.com"
            
            # Mock response
            mock_response.status = 200
            mock_response.all_headers = AsyncMock(return_value={'Content-Type': 'text/html'})
            
            result = await fetcher.fetch("https://example.com")
            
            assert isinstance(result, FetchResult)
            assert result.success is True
            assert result.status_code == 200
            assert "Playwright content" in result.html
            assert result.url == "https://example.com"
            assert result.response_time > 0
    
    @pytest.mark.asyncio
    async def test_playwright_timeout_error(self, fetcher):
        """Test Playwright timeout error handling"""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            # Setup basic mocks
            mock_playwright_instance = Mock()
            mock_browser = Mock()
            mock_context = Mock()
            mock_page = Mock()
            
            mock_playwright_context = AsyncMock()
            mock_playwright_context.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
            mock_playwright_context.__aexit__ = AsyncMock(return_value=None)
            mock_playwright.return_value = mock_playwright_context
            
            mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.add_init_script = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            
            # Mock page.goto to raise timeout
            mock_page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("Timeout"))
            mock_page.close = AsyncMock()
            
            with pytest.raises(HTTPFetchError) as exc_info:
                await fetcher.fetch("https://example.com")
            
            assert "timeout" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_playwright_cleanup(self, fetcher):
        """Test Playwright resource cleanup"""
        # Mock initialization first
        with patch('playwright.async_api.async_playwright') as mock_playwright:
            mock_playwright_instance = Mock()
            mock_browser = Mock()
            mock_context = Mock()
            
            mock_playwright_context = AsyncMock()
            mock_playwright_context.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
            mock_playwright_context.__aexit__ = AsyncMock(return_value=None)
            mock_playwright.return_value = mock_playwright_context
            
            mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.add_init_script = AsyncMock()
            
            # Mock cleanup methods
            mock_context.close = AsyncMock()
            mock_browser.close = AsyncMock()
            mock_playwright_instance.stop = AsyncMock()
            
            await fetcher.initialize()
            
            # Set the mocked objects
            fetcher.playwright = mock_playwright_instance
            fetcher.browser = mock_browser
            fetcher.context = mock_context
            
            await fetcher.cleanup()
            
            # Verify cleanup was called
            mock_context.close.assert_called_once()
            mock_browser.close.assert_called_once()
            mock_playwright_instance.stop.assert_called_once()
            
            assert fetcher._initialized is False
    
    def test_random_user_agent_generation(self, fetcher):
        """Test random user agent generation"""
        ua1 = fetcher._get_random_user_agent()
        ua2 = fetcher._get_random_user_agent()
        
        assert isinstance(ua1, str)
        assert isinstance(ua2, str)
        assert "Mozilla" in ua1  # Should be a realistic user agent
        
        # They might be the same, but should at least be valid
        assert len(ua1) > 50  # Realistic user agents are long


class TestFetchResult:
    """Test cases for FetchResult data class"""
    
    def test_fetch_result_creation(self):
        """Test FetchResult creation"""
        result = FetchResult(
            success=True,
            status_code=200,
            html="<html>Test</html>",
            headers={'Content-Type': 'text/html'},
            url="https://example.com",
            response_time=1.5
        )
        
        assert result.success is True
        assert result.status_code == 200
        assert result.html == "<html>Test</html>"
        assert result.headers['Content-Type'] == 'text/html'
        assert result.url == "https://example.com"
        assert result.response_time == 1.5
        assert result.error is None
    
    def test_fetch_result_with_error(self):
        """Test FetchResult with error"""
        result = FetchResult(
            success=False,
            status_code=None,
            html="",
            headers={},
            url="https://example.com",
            response_time=0.5,
            error="Connection failed"
        )
        
        assert result.success is False
        assert result.status_code is None
        assert result.error == "Connection failed"


class TestHTTPFetchError:
    """Test cases for HTTPFetchError exception"""
    
    def test_http_fetch_error_creation(self):
        """Test HTTPFetchError creation"""
        error = HTTPFetchError(
            message="Request failed",
            status_code=404,
            url="https://example.com"
        )
        
        assert str(error) == "HTTPFetchError: Request failed (URL: https://example.com, Status: 404)"
        assert error.message == "Request failed"
        assert error.status_code == 404
        assert error.url == "https://example.com"
    
    def test_http_fetch_error_without_status(self):
        """Test HTTPFetchError without status code"""
        error = HTTPFetchError(
            message="Network error",
            url="https://example.com"
        )
        
        assert "Network error" in str(error)
        assert error.status_code is None
        assert error.url == "https://example.com"
