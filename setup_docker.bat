@echo off
echo Starting Docker containers for Amazon Scraper...

docker-compose up -d

echo Waiting for PostgreSQL to be ready...
timeout /t 10

echo Testing database connection...
docker exec amazon_scraper_postgres pg_isready -U postgres

echo Setup complete! You can now run your scraper.
echo.
echo To stop containers: docker-compose down
echo To view logs: docker logs amazon_scraper_postgres
