"""
Sample HTML data for testing Amazon parser
"""

from typing import List
from crawler.amazon_parser import ProductInfo

# Sample Amazon search results HTML
SAMPLE_AMAZON_SEARCH_HTML = """
<div data-component-type="s-search-result" data-asin="B08N5WRWNW">
    <div class="s-widget-container">
        <div class="s-card-container">
            <h2 class="a-size-mini s-spacing-none s-color-base">
                <a class="a-link-normal s-underline-text s-underline-link-text s-link-style a-text-normal" 
                   href="/dp/B08N5WRWNW/ref=sr_1_1?keywords=wireless+headphones">
                    <span class="a-size-medium a-color-base a-text-normal">
                        Sony WH-1000XM4 Wireless Premium Noise Canceling Overhead Headphones
                    </span>
                </a>
            </h2>
            <div class="a-section a-spacing-none a-spacing-top-small">
                <div class="a-row a-size-small">
                    <span aria-label="4.4 out of 5 stars">
                        <span class="a-icon-alt">4.4 out of 5 stars</span>
                    </span>
                    <span aria-label="73,284 ratings">
                        <a class="a-link-normal" href="#customerReviews">73,284</a>
                    </span>
                </div>
            </div>
            <div class="a-section a-spacing-none a-spacing-top-micro">
                <div class="a-row a-size-base a-color-base">
                    <span class="a-price" data-a-size="xl" data-a-color="base">
                        <span class="a-offscreen">$248.00</span>
                        <span aria-hidden="true">
                            <span class="a-price-symbol">$</span>
                            <span class="a-price-whole">248</span>
                            <span class="a-price-fraction">00</span>
                        </span>
                    </span>
                </div>
            </div>
            <div class="a-row a-spacing-top-small a-spacing-bottom-small">
                <span class="a-color-secondary a-text-strike">$349.99</span>
                <span class="a-color-prime">Prime</span>
            </div>
            <div class="s-image-container">
                <img class="s-image" src="https://m.media-amazon.com/images/I/71o8Q5XJS5L._AC_UY218_.jpg" 
                     alt="Sony WH-1000XM4 Headphones" />
            </div>
        </div>
    </div>
</div>

<div data-component-type="s-search-result" data-asin="B0756CYWWD">
    <div class="s-widget-container">
        <div class="s-card-container">
            <h2 class="a-size-mini s-spacing-none s-color-base">
                <a class="a-link-normal s-underline-text s-underline-link-text s-link-style a-text-normal" 
                   href="/dp/B0756CYWWD/ref=sr_1_2?keywords=wireless+headphones">
                    <span class="a-size-medium a-color-base a-text-normal">
                        Apple AirPods Pro (2nd Generation) Wireless Earbuds
                    </span>
                </a>
            </h2>
            <div class="a-section a-spacing-none a-spacing-top-small">
                <div class="a-row a-size-small">
                    <span aria-label="4.5 out of 5 stars">
                        <span class="a-icon-alt">4.5 out of 5 stars</span>
                    </span>
                    <span aria-label="89,523 ratings">
                        <a class="a-link-normal" href="#customerReviews">89,523</a>
                    </span>
                </div>
            </div>
            <div class="a-section a-spacing-none a-spacing-top-micro">
                <div class="a-row a-size-base a-color-base">
                    <span class="a-price" data-a-size="xl" data-a-color="base">
                        <span class="a-offscreen">$199.00</span>
                        <span aria-hidden="true">
                            <span class="a-price-symbol">$</span>
                            <span class="a-price-whole">199</span>
                            <span class="a-price-fraction">00</span>
                        </span>
                    </span>
                </div>
            </div>
            <div class="a-row a-spacing-top-small a-spacing-bottom-small">
                <span class="a-color-prime">Prime</span>
                <div class="AdHolder">
                    <span class="a-color-secondary">Sponsored</span>
                </div>
            </div>
            <div class="s-image-container">
                <img class="s-image" src="https://m.media-amazon.com/images/I/61SUj2aKoEL._AC_UY218_.jpg" 
                     alt="Apple AirPods Pro" />
            </div>
        </div>
    </div>
</div>
"""

# Sample individual product page HTML
SAMPLE_PRODUCT_PAGE_HTML = """
<div id="dp-container">
    <div id="centerCol">
        <div id="feature-bullets">
            <h1 id="title" class="a-size-large">
                <span id="productTitle" class="a-size-large product-title-word-break">
                    Sony WH-1000XM4 Wireless Premium Noise Canceling Overhead Headphones with Mic for Phone-Call
                </span>
            </h1>
            
            <div id="averageCustomerReviews" data-hook="average-customer-reviews">
                <span data-hook="rating-out-of-text">4.4 out of 5 stars</span>
                <span data-hook="total-review-count">73,284 ratings</span>
            </div>
            
            <div class="a-section a-spacing-small a-spacing-top-small">
                <span class="a-price a-text-price a-size-medium a-color-price">
                    <span class="a-offscreen">$248.00</span>
                </span>
            </div>
            
            <div id="availability" class="a-section a-spacing-base">
                <span class="a-color-success">In Stock</span>
            </div>
            
            <div id="primePopover">
                <span class="a-color-prime">Prime</span>
            </div>
        </div>
    </div>
    
    <div id="leftCol">
        <img id="landingImage" src="https://m.media-amazon.com/images/I/71o8Q5XJS5L._AC_SX425_.jpg" 
             alt="Sony WH-1000XM4" />
    </div>
</div>
"""

# Sample CAPTCHA challenge HTML
SAMPLE_CAPTCHA_HTML = """
<html>
<head>
    <title>Robot Check</title>
</head>
<body>
    <div class="a-container a-padding-double-large">
        <div class="a-section">
            <div class="a-box a-alert a-alert-info a-spacing-base">
                <div class="a-box-inner a-alert-container">
                    <h4>Type the characters you see in this image:</h4>
                    <div class="a-row a-spacing-large">
                        <img src="/captcha/Captcha_1234567890.jpg" alt="captcha" />
                    </div>
                    <div class="a-row a-spacing-base">
                        <div class="a-column a-span6">
                            <form method="post" action="/errors/validateCaptcha">
                                <input type="hidden" name="amzn" value="abc123xyz" />
                                <input type="hidden" name="amzn-r" value="/s?k=headphones" />
                                <input type="text" id="captchacharacters" name="field-keywords" 
                                       placeholder="Type characters" autocomplete="off" spellcheck="false" />
                                <button type="submit" class="a-button-primary">Continue shopping</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

# Sample blocked/rate limited HTML
SAMPLE_BLOCKED_HTML = """
<html>
<head>
    <title>Sorry! Something went wrong!</title>
</head>
<body>
    <div class="a-container">
        <div class="a-section">
            <h1>Sorry! Something went wrong!</h1>
            <p>
                We apologize for the inconvenience. Your access has been temporarily restricted 
                due to unusual activity. Please try again later.
            </p>
            <p>
                Reference ID: 1234567890abcdef
            </p>
        </div>
    </div>
</body>
</html>
"""

def get_sample_product_info() -> List[ProductInfo]:
    """Get sample ProductInfo objects for testing"""
    return [
        ProductInfo(
            title="Sony WH-1000XM4 Wireless Premium Noise Canceling Overhead Headphones",
            price="$248.00",
            rating=4.4,
            num_reviews=73284,
            product_url="/dp/B08N5WRWNW/ref=sr_1_1?keywords=wireless+headphones",
            image_url="https://m.media-amazon.com/images/I/71o8Q5XJS5L._AC_UY218_.jpg",
            prime_eligible=True,
            sponsored=False,
            availability="In Stock",
            brand="Sony",
            category="Electronics"
        ),
        ProductInfo(
            title="Apple AirPods Pro (2nd Generation) Wireless Earbuds",
            price="$199.00",
            rating=4.5,
            num_reviews=89523,
            product_url="/dp/B0756CYWWD/ref=sr_1_2?keywords=wireless+headphones",
            image_url="https://m.media-amazon.com/images/I/61SUj2aKoEL._AC_UY218_.jpg",
            prime_eligible=True,
            sponsored=True,
            availability="In Stock",
            brand="Apple",
            category="Electronics"
        )
    ]
