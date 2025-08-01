import random
import requests

def load_proxies():
    # These are some free HTTP proxies (they change frequently)
    # For production, use paid residential proxies
    return [
        "http://8.208.84.236:3128",
        "http://20.111.54.16:80", 
        "http://47.88.11.3:8080",
        "http://8.219.97.248:80",
        # Add more working proxies here
    ]

def test_proxy(proxy):
    """Test if a proxy is working"""
    try:
        response = requests.get("http://httpbin.org/ip", 
                              proxies={"http": proxy, "https": proxy}, 
                              timeout=10)
        return response.status_code == 200
    except:
        return False

def get_working_proxy(proxies):
    """Get a working proxy from the list"""
    random.shuffle(proxies)
    for proxy in proxies:
        if test_proxy(proxy):
            return proxy
    return None

def get_random_proxy(proxies):
    return random.choice(proxies)
