-- Create the products table
CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    product_name TEXT,
    price NUMERIC(10,2),
    rating NUMERIC(3,2),
    reviews_count INTEGER,
    product_url TEXT UNIQUE NOT NULL,
    keyword TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create unique index on product_url for upserts
CREATE UNIQUE INDEX IF NOT EXISTS idx_products_url ON products(product_url);

-- Create index on keyword for faster queries
CREATE INDEX IF NOT EXISTS idx_products_keyword ON products(keyword);

-- Create index on scraped_at for time-based queries
CREATE INDEX IF NOT EXISTS idx_products_scraped_at ON products(scraped_at);
