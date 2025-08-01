-- Initialize Amazon Scraper Database
-- This script runs when the PostgreSQL container starts for the first time

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create additional users if needed
-- CREATE USER scraper_read_only WITH PASSWORD 'readonly_password';

-- Create additional databases for testing
CREATE DATABASE amazon_scraper_test;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE amazon_scraper TO scraper_user;
GRANT ALL PRIVILEGES ON DATABASE amazon_scraper_test TO scraper_user;

-- Connect to main database for additional setup
\c amazon_scraper;

-- Create schemas if needed
-- CREATE SCHEMA IF NOT EXISTS analytics;
-- CREATE SCHEMA IF NOT EXISTS reporting;

-- Grant permissions on schemas
-- GRANT USAGE ON SCHEMA analytics TO scraper_user;
-- GRANT CREATE ON SCHEMA analytics TO scraper_user;

-- Set default configuration
ALTER DATABASE amazon_scraper SET timezone = 'UTC';

-- Performance tuning (adjust based on your system)
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET work_mem = '4MB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';

-- Reload configuration
SELECT pg_reload_conf();

-- Create indexes that will be commonly used
-- These will be created by SQLAlchemy, but we can prepare them here if needed

-- Create a function to clean up old data (optional)
CREATE OR REPLACE FUNCTION cleanup_old_fetch_logs(older_than_days INTEGER DEFAULT 30)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM fetch_logs 
    WHERE timestamp < (CURRENT_TIMESTAMP - INTERVAL '1 day' * older_than_days);
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$;

-- Create a function to get database statistics
CREATE OR REPLACE FUNCTION get_scraper_stats()
RETURNS TABLE(
    table_name TEXT,
    row_count BIGINT,
    table_size TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        schemaname || '.' || tablename AS table_name,
        n_tup_ins - n_tup_del AS row_count,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS table_size
    FROM pg_stat_user_tables
    ORDER BY n_tup_ins - n_tup_del DESC;
END;
$$;

-- Log initialization completion
DO $$
BEGIN
    RAISE NOTICE 'Amazon Scraper database initialization completed at %', NOW();
END $$;
