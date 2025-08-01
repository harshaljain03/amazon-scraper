"""
CAPTCHA Detection and Solving Module for Amazon Scraper
Detects various CAPTCHA challenges and provides solving interface
"""

import re
import logging
import asyncio
import base64
import time
from typing import Dict, List, Optional, Tuple, Union, Any
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod

from playwright.async_api import Page, ElementHandle
from bs4 import BeautifulSoup


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CaptchaType(Enum):
    """Types of CAPTCHA challenges"""
    NONE = "none"
    IMAGE_TEXT = "image_text"
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    AMAZON_IMAGE = "amazon_image"
    AMAZON_AUDIO = "amazon_audio"
    FUNCAPTCHA = "funcaptcha"
    CLOUDFLARE = "cloudflare"
    UNKNOWN = "unknown"


@dataclass
class CaptchaChallenge:
    """Data class for CAPTCHA challenge information"""
    captcha_type: CaptchaType
    detected: bool = False
    confidence: float = 0.0
    image_url: str = None
    image_base64: str = None
    site_key: str = None
    challenge_text: str = None
    form_action: str = None
    form_data: Dict[str, str] = None
    solution_field: str = None
    additional_data: Dict[str, Any] = None


class CaptchaSolver(ABC):
    """Abstract base class for CAPTCHA solving services"""
    
    @abstractmethod
    async def solve_image_captcha(self, image_data: str, challenge_text: str = None) -> Optional[str]:
        """Solve image-based CAPTCHA"""
        pass
    
    @abstractmethod
    async def solve_recaptcha_v2(self, site_key: str, page_url: str) -> Optional[str]:
        """Solve reCAPTCHA v2"""
        pass
    
    @abstractmethod
    async def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "verify") -> Optional[str]:
        """Solve reCAPTCHA v3"""
        pass
    
    @abstractmethod
    async def get_balance(self) -> float:
        """Get account balance"""
        pass


class CaptchaDetector:
    """
    Detects various CAPTCHA challenges in web pages
    Specialized for Amazon and common CAPTCHA services
    """
    
    def __init__(self):
        """Initialize CAPTCHA detector"""
        
        # Amazon-specific CAPTCHA patterns
        self.amazon_patterns = {
            'captcha_page_indicators': [
                r'Type the characters you see in this image',
                r'Enter the characters you see below',
                r'To continue shopping, please type the characters',
                r'captcha',
                r'security check',
                r'robot check'
            ],
            'captcha_image_selectors': [
                'img[alt*="captcha"]',
                'img[src*="captcha"]',
                'img[id*="captcha"]',
                '#captchacharacters + img',
                '.a-captcha-image img',
                'img[alt*="Type the characters"]'
            ],
            'captcha_input_selectors': [
                'input[id*="captcha"]',
                'input[name*="captcha"]',
                '#captchacharacters',
                'input[placeholder*="captcha"]',
                'input[aria-label*="captcha"]'
            ],
            'form_selectors': [
                'form[action*="captcha"]',
                'form[method="post"]',
                'form[name*="captcha"]'
            ]
        }
        
        # Generic CAPTCHA service patterns
        self.service_patterns = {
            'recaptcha_v2': [
                'div.g-recaptcha',
                'iframe[src*="recaptcha"]',
                'script[src*="recaptcha"]'
            ],
            'recaptcha_v3': [
                'script[src*="recaptcha/releases/"]',
                'grecaptcha.execute'
            ],
            'hcaptcha': [
                'div.h-captcha',
                'iframe[src*="hcaptcha"]',
                'script[src*="hcaptcha"]'
            ],
            'funcaptcha': [
                'div#funcaptcha',
                'iframe[src*="funcaptcha"]',
                'script[src*="arkoselabs"]'
            ],
            'cloudflare': [
                'div.cf-challenge-form',
                'div.cf-browser-verification',
                'script[src*="cloudflare"]'
            ]
        }
    
    async def detect_captcha(self, page: Page, html: str = None) -> CaptchaChallenge:
        """
        Detect CAPTCHA challenges on a page
        
        Args:
            page: Playwright Page object
            html: Optional HTML content for additional parsing
            
        Returns:
            CaptchaChallenge object with detection results
        """
        try:
            # Get page content if not provided
            if html is None:
                html = await page.content()
            
            # Check for Amazon-specific CAPTCHAs first
            amazon_result = await self._detect_amazon_captcha(page, html)
            if amazon_result.detected:
                return amazon_result
            
            # Check for service-based CAPTCHAs
            service_result = await self._detect_service_captcha(page, html)
            if service_result.detected:
                return service_result
            
            # No CAPTCHA detected
            return CaptchaChallenge(captcha_type=CaptchaType.NONE)
            
        except Exception as e:
            logger.error(f"Error detecting CAPTCHA: {e}")
            return CaptchaChallenge(
                captcha_type=CaptchaType.UNKNOWN,
                detected=True,
                confidence=0.1,
                additional_data={'error': str(e)}
            )
    
    async def _detect_amazon_captcha(self, page: Page, html: str) -> CaptchaChallenge:
        """Detect Amazon-specific CAPTCHA challenges"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check for text indicators
        text_confidence = 0.0
        for pattern in self.amazon_patterns['captcha_page_indicators']:
            if re.search(pattern, html, re.IGNORECASE):
                text_confidence += 0.2
        
        # Check for CAPTCHA images
        image_element = None
        image_confidence = 0.0
        
        for selector in self.amazon_patterns['captcha_image_selectors']:
            try:
                element = await page.query_selector(selector)
                if element:
                    image_element = element
                    image_confidence = 0.5
                    break
            except Exception:
                continue
        
        # Check for input fields
        input_element = None
        input_confidence = 0.0
        
        for selector in self.amazon_patterns['captcha_input_selectors']:
            try:
                element = await page.query_selector(selector)
                if element:
                    input_element = element
                    input_confidence = 0.3
                    break
            except Exception:
                continue
        
        # Calculate overall confidence
        total_confidence = text_confidence + image_confidence + input_confidence
        
        if total_confidence >= 0.5:  # Threshold for detection
            # Extract additional information
            image_data = await self._extract_image_data(image_element) if image_element else None
            form_data = await self._extract_form_data(page)
            challenge_text = await self._extract_challenge_text(page, html)
            
            return CaptchaChallenge(
                captcha_type=CaptchaType.AMAZON_IMAGE,
                detected=True,
                confidence=min(total_confidence, 1.0),
                image_base64=image_data,
                challenge_text=challenge_text,
                form_data=form_data,
                solution_field=await self._get_input_name(input_element) if input_element else None
            )
        
        return CaptchaChallenge(captcha_type=CaptchaType.NONE)
    
    async def _detect_service_captcha(self, page: Page, html: str) -> CaptchaChallenge:
        """Detect service-based CAPTCHA challenges (reCAPTCHA, hCaptcha, etc.)"""
        
        # Check reCAPTCHA v2
        for selector in self.service_patterns['recaptcha_v2']:
            try:
                element = await page.query_selector(selector)
                if element:
                    site_key = await self._extract_recaptcha_site_key(element, html)
                    return CaptchaChallenge(
                        captcha_type=CaptchaType.RECAPTCHA_V2,
                        detected=True,
                        confidence=0.9,
                        site_key=site_key
                    )
            except Exception:
                continue
        
        # Check reCAPTCHA v3
        if any(pattern in html for pattern in ['grecaptcha.execute', 'recaptcha/releases/']):
            site_key = self._extract_recaptcha_v3_site_key(html)
            return CaptchaChallenge(
                captcha_type=CaptchaType.RECAPTCHA_V3,
                detected=True,
                confidence=0.8,
                site_key=site_key
            )
        
        # Check hCaptcha
        for selector in self.service_patterns['hcaptcha']:
            try:
                element = await page.query_selector(selector)
                if element:
                    site_key = await self._extract_hcaptcha_site_key(element)
                    return CaptchaChallenge(
                        captcha_type=CaptchaType.HCAPTCHA,
                        detected=True,
                        confidence=0.9,
                        site_key=site_key
                    )
            except Exception:
                continue
        
        return CaptchaChallenge(captcha_type=CaptchaType.NONE)
    
    async def _extract_image_data(self, image_element: ElementHandle) -> Optional[str]:
        """Extract base64 image data from CAPTCHA image"""
        try:
            # Get image source
            src = await image_element.get_attribute('src')
            if not src:
                return None
            
            # If it's already base64, return it
            if src.startswith('data:image'):
                return src.split(',', 1)[1] if ',' in src else src
            
            # If it's a URL, we need to screenshot the element
            screenshot = await image_element.screenshot()
            return base64.b64encode(screenshot).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error extracting image data: {e}")
            return None
    
    async def _extract_form_data(self, page: Page) -> Dict[str, str]:
        """Extract form data for CAPTCHA submission"""
        form_data = {}
        
        try:
            # Find form elements
            forms = await page.query_selector_all('form')
            for form in forms:
                # Get form action
                action = await form.get_attribute('action')
                if action:
                    form_data['action'] = action
                
                # Get hidden inputs
                hidden_inputs = await form.query_selector_all('input[type="hidden"]')
                for hidden_input in hidden_inputs:
                    name = await hidden_input.get_attribute('name')
                    value = await hidden_input.get_attribute('value')
                    if name and value:
                        form_data[name] = value
        
        except Exception as e:
            logger.error(f"Error extracting form data: {e}")
        
        return form_data
    
    async def _extract_challenge_text(self, page: Page, html: str) -> Optional[str]:
        """Extract challenge text/instructions"""
        challenge_patterns = [
            r'Type the characters you see in this image:?\s*([^<\n]+)',
            r'Enter the characters you see below:?\s*([^<\n]+)',
            r'Please type the letters you see:?\s*([^<\n]+)'
        ]
        
        for pattern in challenge_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    async def _get_input_name(self, input_element: ElementHandle) -> Optional[str]:
        """Get input field name for solution submission"""
        try:
            return await input_element.get_attribute('name') or await input_element.get_attribute('id')
        except Exception:
            return None
    
    async def _extract_recaptcha_site_key(self, element: ElementHandle, html: str) -> Optional[str]:
        """Extract reCAPTCHA site key"""
        try:
            # Try to get from element attribute
            site_key = await element.get_attribute('data-sitekey')
            if site_key:
                return site_key
            
            # Try to extract from HTML
            pattern = r'data-sitekey=["\']([^"\']+)["\']'
            match = re.search(pattern, html)
            if match:
                return match.group(1)
            
        except Exception:
            pass
        
        return None
    
    def _extract_recaptcha_v3_site_key(self, html: str) -> Optional[str]:
        """Extract reCAPTCHA v3 site key from HTML"""
        patterns = [
            r'grecaptcha\.execute\(["\']([^"\']+)["\']',
            r'data-sitekey=["\']([^"\']+)["\']'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        
        return None
    
    async def _extract_hcaptcha_site_key(self, element: ElementHandle) -> Optional[str]:
        """Extract hCaptcha site key"""
        try:
            return await element.get_attribute('data-sitekey')
        except Exception:
            return None


class TwoCaptchaSolver(CaptchaSolver):
    """
    2Captcha service integration for solving CAPTCHAs
    Production implementation with real API calls
    """
    
    def __init__(self, api_key: str, base_url: str = "https://2captcha.com"):
        """
        Initialize 2Captcha solver
        
        Args:
            api_key: 2Captcha API key
            base_url: 2Captcha API base URL
        """
        self.api_key = api_key
        self.base_url = base_url
        import aiohttp
        self.session = None
    
    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None:
            import aiohttp
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def solve_image_captcha(self, image_data: str, challenge_text: str = None) -> Optional[str]:
        """
        Solve image-based CAPTCHA using 2Captcha
        
        Args:
            image_data: Base64 encoded image data
            challenge_text: Optional challenge instruction text
            
        Returns:
            CAPTCHA solution text or None if failed
        """
        try:
            session = await self._get_session()
            
            logger.info("Submitting image CAPTCHA to 2Captcha service")
            
            # Submit CAPTCHA
            submit_data = {
                'method': 'base64',
                'key': self.api_key,
                'body': image_data,
                'json': 1
            }
            
            if challenge_text:
                submit_data['textinstructions'] = challenge_text
            
            async with session.post(f"{self.base_url}/in.php", data=submit_data) as response:
                result = await response.json()
                
                if result.get('status') != 1:
                    logger.error(f"Failed to submit CAPTCHA: {result}")
                    return None
                
                captcha_id = result.get('request')
                logger.info(f"CAPTCHA submitted with ID: {captcha_id}")
            
            # Poll for result
            max_attempts = 30
            for attempt in range(max_attempts):
                await asyncio.sleep(5)  # Wait before checking
                
                result_data = {
                    'key': self.api_key,
                    'action': 'get',
                    'id': captcha_id,
                    'json': 1
                }
                
                async with session.get(f"{self.base_url}/res.php", params=result_data) as response:
                    result = await response.json()
                    
                    if result.get('status') == 1:
                        solution = result.get('request')
                        logger.info(f"CAPTCHA solved: {solution}")
                        return solution
                    elif result.get('error_text'):
                        logger.error(f"CAPTCHA solving error: {result.get('error_text')}")
                        return None
                
                logger.info(f"Checking CAPTCHA result (attempt {attempt + 1})")
            
            logger.error("CAPTCHA solving timeout")
            return None
            
        except Exception as e:
            logger.error(f"Error solving image CAPTCHA: {e}")
            return None
    
    async def solve_recaptcha_v2(self, site_key: str, page_url: str) -> Optional[str]:
        """
        Solve reCAPTCHA v2 using 2Captcha
        
        Args:
            site_key: reCAPTCHA site key
            page_url: Page URL where reCAPTCHA is located
            
        Returns:
            reCAPTCHA token or None if failed
        """
        try:
            session = await self._get_session()
            
            logger.info(f"Solving reCAPTCHA v2 for site key: {site_key}")
            
            # Submit reCAPTCHA
            submit_data = {
                'method': 'userrecaptcha',
                'key': self.api_key,
                'googlekey': site_key,
                'pageurl': page_url,
                'json': 1
            }
            
            async with session.post(f"{self.base_url}/in.php", data=submit_data) as response:
                result = await response.json()
                
                if result.get('status') != 1:
                    logger.error(f"Failed to submit reCAPTCHA: {result}")
                    return None
                
                captcha_id = result.get('request')
                logger.info(f"reCAPTCHA submitted with ID: {captcha_id}")
            
            # Poll for result
            for attempt in range(60):  # reCAPTCHA can take longer
                await asyncio.sleep(5)
                
                result_data = {
                    'key': self.api_key,
                    'action': 'get',
                    'id': captcha_id,
                    'json': 1
                }
                
                async with session.get(f"{self.base_url}/res.php", params=result_data) as response:
                    result = await response.json()
                    
                    if result.get('status') == 1:
                        token = result.get('request')
                        logger.info("reCAPTCHA solved successfully")
                        return token
                    elif result.get('error_text'):
                        logger.error(f"reCAPTCHA solving error: {result.get('error_text')}")
                        return None
                
                logger.info(f"Checking reCAPTCHA result (attempt {attempt + 1})")
            
            logger.error("reCAPTCHA solving timeout")
            return None
            
        except Exception as e:
            logger.error(f"Error solving reCAPTCHA v2: {e}")
            return None
    
    async def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "verify") -> Optional[str]:
        """
        Solve reCAPTCHA v3 using 2Captcha
        
        Args:
            site_key: reCAPTCHA site key
            page_url: Page URL
            action: reCAPTCHA action
            
        Returns:
            reCAPTCHA token or None if failed
        """
        try:
            session = await self._get_session()
            
            logger.info(f"Solving reCAPTCHA v3 for site key: {site_key}")
            
            submit_data = {
                'method': 'userrecaptcha',
                'key': self.api_key,
                'googlekey': site_key,
                'pageurl': page_url,
                'version': 'v3',
                'action': action,
                'min_score': 0.3,
                'json': 1
            }
            
            async with session.post(f"{self.base_url}/in.php", data=submit_data) as response:
                result = await response.json()
                
                if result.get('status') != 1:
                    logger.error(f"Failed to submit reCAPTCHA v3: {result}")
                    return None
                
                captcha_id = result.get('request')
                logger.info(f"reCAPTCHA v3 submitted with ID: {captcha_id}")
            
            # Poll for result
            for attempt in range(60):
                await asyncio.sleep(5)
                
                result_data = {
                    'key': self.api_key,
                    'action': 'get',
                    'id': captcha_id,
                    'json': 1
                }
                
                async with session.get(f"{self.base_url}/res.php", params=result_data) as response:
                    result = await response.json()
                    
                    if result.get('status') == 1:
                        token = result.get('request')
                        logger.info("reCAPTCHA v3 solved successfully")
                        return token
                    elif result.get('error_text'):
                        logger.error(f"reCAPTCHA v3 solving error: {result.get('error_text')}")
                        return None
                
                logger.info(f"Checking reCAPTCHA v3 result (attempt {attempt + 1})")
            
            logger.error("reCAPTCHA v3 solving timeout")
            return None
            
        except Exception as e:
            logger.error(f"Error solving reCAPTCHA v3: {e}")
            return None
    
    async def get_balance(self) -> float:
        """Get account balance"""
        try:
            session = await self._get_session()
            
            params = {
                'key': self.api_key,
                'action': 'getbalance',
                'json': 1
            }
            
            async with session.get(f"{self.base_url}/res.php", params=params) as response:
                result = await response.json()
                
                if result.get('status') == 1:
                    balance = float(result.get('request', 0))
                    logger.info(f"2Captcha balance: ${balance}")
                    return balance
                
                logger.error(f"Failed to get balance: {result}")
                return 0.0
                
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0
    
    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
            self.session = None


class CaptchaHandler:
    """
    Main CAPTCHA handler that coordinates detection and solving
    """
    
    def __init__(self, solver: CaptchaSolver):
        """
        Initialize CAPTCHA handler
        
        Args:
            solver: CaptchaSolver instance for solving challenges
        """
        self.detector = CaptchaDetector()
        self.solver = solver
    
    async def handle_captcha(self, page: Page, page_url: str) -> bool:
        """
        Detect and solve CAPTCHA on a page
        
        Args:
            page: Playwright Page object
            page_url: Current page URL
            
        Returns:
            True if CAPTCHA was solved or none detected, False if failed
        """
        try:
            # Detect CAPTCHA
            challenge = await self.detector.detect_captcha(page)
            
            if not challenge.detected:
                logger.debug("No CAPTCHA detected")
                return True
            
            logger.info(f"CAPTCHA detected: {challenge.captcha_type.value}")
            
            # Solve based on type
            solution = None
            
            if challenge.captcha_type == CaptchaType.AMAZON_IMAGE:
                if challenge.image_base64:
                    solution = await self.solver.solve_image_captcha(
                        challenge.image_base64,
                        challenge.challenge_text
                    )
            
            elif challenge.captcha_type == CaptchaType.RECAPTCHA_V2:
                if challenge.site_key:
                    solution = await self.solver.solve_recaptcha_v2(
                        challenge.site_key,
                        page_url
                    )
            
            elif challenge.captcha_type == CaptchaType.RECAPTCHA_V3:
                if challenge.site_key:
                    solution = await self.solver.solve_recaptcha_v3(
                        challenge.site_key,
                        page_url
                    )
            
            if solution:
                # Submit solution
                success = await self._submit_solution(page, challenge, solution)
                if success:
                    logger.info("CAPTCHA solved and submitted successfully")
                    return True
                else:
                    logger.error("Failed to submit CAPTCHA solution")
                    return False
            else:
                logger.error(f"Failed to solve CAPTCHA: {challenge.captcha_type.value}")
                return False
                
        except Exception as e:
            logger.error(f"Error handling CAPTCHA: {e}")
            return False
    
    async def _submit_solution(self, page: Page, challenge: CaptchaChallenge, solution: str) -> bool:
        """
        Submit CAPTCHA solution to the page
        
        Args:
            page: Playwright Page object
            challenge: CaptchaChallenge with solution details
            solution: Solution string
            
        Returns:
            True if submission succeeded
        """
        try:
            if challenge.captcha_type == CaptchaType.AMAZON_IMAGE:
                # Fill input field
                if challenge.solution_field:
                    input_selector = f'input[name="{challenge.solution_field}"], input[id="{challenge.solution_field}"]'
                    input_element = await page.query_selector(input_selector)
                    
                    if input_element:
                        await input_element.fill(solution)
                        
                        # Submit form
                        await input_element.press('Enter')
                        
                        # Wait for navigation or response
                        await page.wait_for_load_state('networkidle', timeout=10000)
                        
                        return True
            
            elif challenge.captcha_type in [CaptchaType.RECAPTCHA_V2, CaptchaType.RECAPTCHA_V3]:
                # Execute JavaScript to submit reCAPTCHA token
                await page.evaluate(f"""
                    if (typeof grecaptcha !== 'undefined') {{
                        grecaptcha.getResponse = function() {{ return '{solution}'; }};
                    }}
                """)
                
                # Find and click submit button
                submit_selectors = ['input[type="submit"]', 'button[type="submit"]', '.g-recaptcha']
                
                for selector in submit_selectors:
                    button = await page.query_selector(selector)
                    if button:
                        await button.click()
                        await page.wait_for_load_state('networkidle', timeout=10000)
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error submitting CAPTCHA solution: {e}")
            return False
