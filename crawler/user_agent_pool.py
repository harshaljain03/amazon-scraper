"""
User Agent Pool for Amazon Scraper
Provides realistic user agent rotation for anti-detection
"""

import random
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class UserAgentInfo:
    """Information about a user agent"""
    user_agent: str
    browser: str
    platform: str
    mobile: bool = False
    usage_count: int = 0
    last_used: Optional[datetime] = None
    success_rate: float = 1.0


class UserAgentPool:
    """
    Pool of realistic user agents for rotation
    Includes desktop and mobile user agents with usage tracking
    """
    
    def __init__(self, include_mobile: bool = False):
        """
        Initialize user agent pool
        
        Args:
            include_mobile: Whether to include mobile user agents
        """
        self.include_mobile = include_mobile
        self.user_agents: List[UserAgentInfo] = []
        self._initialize_user_agents()
        
        logger.info(f"UserAgentPool initialized with {len(self.user_agents)} user agents")
    
    def _initialize_user_agents(self):
        """Initialize the pool with realistic user agents"""
        
        # Desktop Chrome user agents
        chrome_desktop = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        
        for ua in chrome_desktop:
            if "Windows" in ua:
                platform = "Windows"
            elif "Macintosh" in ua:
                platform = "macOS"
            else:
                platform = "Linux"
            
            self.user_agents.append(UserAgentInfo(
                user_agent=ua,
                browser="Chrome",
                platform=platform,
                mobile=False
            ))
        
        # Desktop Firefox user agents
        firefox_desktop = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        ]
        
        for ua in firefox_desktop:
            if "Windows" in ua:
                platform = "Windows"
            elif "Macintosh" in ua:
                platform = "macOS"
            else:
                platform = "Linux"
            
            self.user_agents.append(UserAgentInfo(
                user_agent=ua,
                browser="Firefox",
                platform=platform,
                mobile=False
            ))
        
        # Desktop Safari user agents
        safari_desktop = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
        ]
        
        for ua in safari_desktop:
            self.user_agents.append(UserAgentInfo(
                user_agent=ua,
                browser="Safari",
                platform="macOS",
                mobile=False
            ))
        
        # Desktop Edge user agents
        edge_desktop = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
        ]
        
        for ua in edge_desktop:
            platform = "Windows" if "Windows" in ua else "macOS"
            self.user_agents.append(UserAgentInfo(
                user_agent=ua,
                browser="Edge",
                platform=platform,
                mobile=False
            ))
        
        # Mobile user agents (if enabled)
        if self.include_mobile:
            mobile_user_agents = [
                # Mobile Chrome
                "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                "Mozilla/5.0 (Linux; Android 12; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                
                # iPhone Safari
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                
                # iPad Safari
                "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            ]
            
            for ua in mobile_user_agents:
                if "Android" in ua:
                    platform = "Android"
                    browser = "Chrome" if "Chrome" in ua else "Android Browser"
                elif "iPhone" in ua or "iPad" in ua:
                    platform = "iOS"
                    browser = "Safari"
                else:
                    platform = "Mobile"
                    browser = "Mobile Browser"
                
                self.user_agents.append(UserAgentInfo(
                    user_agent=ua,
                    browser=browser,
                    platform=platform,
                    mobile=True
                ))
    
    def get_random_user_agent(self, mobile_only: bool = False, desktop_only: bool = False) -> str:
        """
        Get a random user agent string
        
        Args:
            mobile_only: Only return mobile user agents
            desktop_only: Only return desktop user agents
            
        Returns:
            User agent string
        """
        available_agents = self.user_agents
        
        if mobile_only:
            available_agents = [ua for ua in self.user_agents if ua.mobile]
        elif desktop_only:
            available_agents = [ua for ua in self.user_agents if not ua.mobile]
        
        if not available_agents:
            # Fallback to default Chrome user agent
            return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        # Weight selection by success rate and recency
        weights = []
        now = datetime.now()
        
        for ua_info in available_agents:
            # Base weight on success rate
            weight = ua_info.success_rate
            
            # Reduce weight for recently used agents
            if ua_info.last_used:
                hours_since_use = (now - ua_info.last_used).total_seconds() / 3600
                if hours_since_use < 1:  # Used within last hour
                    weight *= 0.5
                elif hours_since_use < 6:  # Used within last 6 hours
                    weight *= 0.8
            
            # Reduce weight for heavily used agents
            if ua_info.usage_count > 100:
                weight *= 0.7
            
            weights.append(max(weight, 0.1))  # Minimum weight to ensure all agents can be selected
        
        # Select based on weights
        selected_ua = random.choices(available_agents, weights=weights)[0]
        
        # Update usage statistics
        selected_ua.usage_count += 1
        selected_ua.last_used = now
        
        logger.debug(f"Selected user agent: {selected_ua.browser} on {selected_ua.platform}")
        
        return selected_ua.user_agent
    
    def get_user_agent_by_browser(self, browser: str) -> Optional[str]:
        """
        Get a user agent for a specific browser
        
        Args:
            browser: Browser name (Chrome, Firefox, Safari, Edge)
            
        Returns:
            User agent string or None if not found
        """
        matching_agents = [ua for ua in self.user_agents if ua.browser.lower() == browser.lower()]
        
        if not matching_agents:
            return None
        
        selected_ua = random.choice(matching_agents)
        selected_ua.usage_count += 1
        selected_ua.last_used = datetime.now()
        
        return selected_ua.user_agent
    
    def update_success_rate(self, user_agent: str, success: bool):
        """
        Update success rate for a user agent based on request outcome
        
        Args:
            user_agent: User agent string
            success: Whether the request was successful
        """
        for ua_info in self.user_agents:
            if ua_info.user_agent == user_agent:
                # Use exponential moving average for success rate
                alpha = 0.1  # Learning rate
                new_rate = 1.0 if success else 0.0
                ua_info.success_rate = (1 - alpha) * ua_info.success_rate + alpha * new_rate
                
                logger.debug(f"Updated success rate for {ua_info.browser}: {ua_info.success_rate:.2f}")
                break
    
    def get_statistics(self) -> Dict[str, any]:
        """
        Get usage statistics for the user agent pool
        
        Returns:
            Dictionary with statistics
        """
        total_usage = sum(ua.usage_count for ua in self.user_agents)
        
        browser_stats = {}
        platform_stats = {}
        
        for ua_info in self.user_agents:
            # Browser statistics
            if ua_info.browser not in browser_stats:
                browser_stats[ua_info.browser] = {
                    'count': 0,
                    'usage': 0,
                    'avg_success_rate': 0.0
                }
            
            browser_stats[ua_info.browser]['count'] += 1
            browser_stats[ua_info.browser]['usage'] += ua_info.usage_count
            browser_stats[ua_info.browser]['avg_success_rate'] += ua_info.success_rate
            
            # Platform statistics
            if ua_info.platform not in platform_stats:
                platform_stats[ua_info.platform] = {
                    'count': 0,
                    'usage': 0,
                    'mobile': 0
                }
            
            platform_stats[ua_info.platform]['count'] += 1
            platform_stats[ua_info.platform]['usage'] += ua_info.usage_count
            if ua_info.mobile:
                platform_stats[ua_info.platform]['mobile'] += 1
        
        # Calculate averages
        for browser_data in browser_stats.values():
            browser_data['avg_success_rate'] /= browser_data['count']
        
        return {
            'total_agents': len(self.user_agents),
            'total_usage': total_usage,
            'mobile_agents': len([ua for ua in self.user_agents if ua.mobile]),
            'desktop_agents': len([ua for ua in self.user_agents if not ua.mobile]),
            'browser_stats': browser_stats,
            'platform_stats': platform_stats
        }
    
    def reset_usage_statistics(self):
        """Reset all usage statistics"""
        for ua_info in self.user_agents:
            ua_info.usage_count = 0
            ua_info.last_used = None
            ua_info.success_rate = 1.0
        
        logger.info("User agent usage statistics reset")


# Convenience functions
def get_random_desktop_user_agent() -> str:
    """Get a random desktop user agent"""
    pool = UserAgentPool(include_mobile=False)
    return pool.get_random_user_agent()


def get_random_mobile_user_agent() -> str:
    """Get a random mobile user agent"""
    pool = UserAgentPool(include_mobile=True)
    return pool.get_random_user_agent(mobile_only=True)


def get_chrome_user_agent() -> str:
    """Get a Chrome user agent"""
    pool = UserAgentPool()
    return pool.get_user_agent_by_browser("Chrome") or get_random_desktop_user_agent()
