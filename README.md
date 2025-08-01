# 🛒 Amazon Product Scraper

## 🚀 Getting Started & Usage

Here's everything you need to get your Amazon scraper up and running with full monitoring and database storage!

### 1. Prerequisites

- **Python** (Recommended `Python 3.12` to avoid build problems)
- **Docker Desktop** (For running PostgreSQL, Redis, and monitoring stack)
- **Git** (To download/clone this repo)
- **Shell** (Bash, PowerShell, or Command Prompt)

### 2. Clone the Repository

```
git clone https://github.com/harshaljain03/amazon-scraper.git
cd amazon-scraper
```

### 3. Set Up Python Environment

Create a Python Virtual Environment (recommended):
```
python -m venv venv
venv/Scripts/active # On Windows

venv/bin/activate # On Linux/OSX
pip install -r requirements.txt
```
If errors continue:
- Download Visual Studio C++ Build Tools and make sure to select the given components:
  - "C++ build tools" workload
  - MSVC v143 - VS 2022 C++ x64/x86 build tools
  - Windows 11 SDK
  - CMake tools for Visual Studio (Optional but helpful)

### 4. Install Playwright Browsers

Download the headless browsers used for scraping:
```
playwright install
```


Once installed, verify the browser installation:
```
playwright install --dry-run
```


### 5. Start Database & Monitoring with Docker

```
docker-compose up -d #Make sure your docker engines are running beforehand
```
This runs PostgreSQL, Redis, pgAdmin, and Grafana - the core data storage and monitoring stack for your scraper.

You can check the running processes by:
```
docker ps
```

### 6. Test Your Scraper Dashboard

Open your web browser and go to:

- **Database Management:** http://localhost:8080 (pgAdmin - admin@admin.com / mypassword123)
- **Metrics Dashboard:** http://localhost:3000 (Grafana - admin / admin123)
- **Prometheus Metrics:** http://localhost:8000/metrics

**What this does:**
- Opens your scraper control panel
- Shows real-time metrics about scraping performance
- Displays database content, success rates, and system health

### 7. Send Your First Scraping Mission!

We're going to start your first Amazon scraping task and watch it work in real-time!
```
python -m crawler.scraper
```
Visit [http://localhost:8080](http://localhost:8080) for pgAdmin Service where you can directly view the database!
Visit [http://localhost:8000/metrics](http://localhost:8000/metrics) for Prometheus metrics!
Visit [http://localhost:3000](http://localhost:3000) for Grafana dashboards!
### 8. Configure Your Environment

Edit the file named `.env` in the project root. Adjust settings (like database passwords or proxy configurations) if needed.

---
## 📁 Project Structure

| Folder/File                   | Purpose                                                        |
|-------------------------------|---------------------------------------------------------------|
| `crawler/scraper.py`          | Main scraping engine with Playwright browser automation       |
| `crawler/parser.py`           | HTML parsing logic for extracting product data                |
| `crawler/proxies.py`          | Proxy rotation and management system                           |
| `data_pipeline/database.py`   | PostgreSQL database models and operations                      |
| `data_pipeline/queue.py`      | Redis queue system for distributed processing                 |
| `monitoring/metrics.py`       | Prometheus metrics collection and export                      |
| `monitoring/alerts.py`        | Alert system for scraper failures and health checks           |
| `jobs/scheduler.py`           | Automated scheduling with APScheduler                         |
| `config/config.yaml`          | Configuration settings and parameters                          |
| `.env`                        | Environment variables: DB credentials, proxy settings         |
| `docker-compose.yml`          | Docker setup for PostgreSQL, Redis, pgAdmin, Grafana         |
| `requirements.txt`            | Python dependencies                                            |

*Every folder represents a core component of your Amazon scraping system!*

---

## ❓ FAQ

**Q:** *Is this legal?*  
**A:** Always respect robots.txt and terms of service. This is for educational purposes. Use responsibly and obtain permission when required.

**Q:** *Why use Docker?*  
**A:** Docker provides easy setup for PostgreSQL, Redis, and monitoring tools without manual installation.

**Q:** *Can I scrape other sites?*  
**A:** Yes! Modify the `parser.py` file with different CSS selectors for other e-commerce sites.

**Q:** *How to handle captchas?*  
**A:** The system includes retry logic and proxy rotation. For production, consider captcha-solving services like 2Captcha.

**Q:** *Where is scraped data stored?*  
**A:** In the `products` table of PostgreSQL database. Access via pgAdmin at http://localhost:8080

**Q:** *How to scale up scraping?*  
**A:** Use the queue-based mode with multiple worker processes, or deploy on Kubernetes for horizontal scaling.

---

## 🤝 Contributing

- **New to Web Scraping?** Read through the code, test with small samples, and ask questions!
- **Find a bug?** Open an issue on GitHub with scraper logs and error details.
- **Want to improve?** Fork the repo, add features (new parsers, monitoring, etc.), and submit a Pull Request.
- **Add new sites?** Create new parser modules following the existing pattern.

---

## 📝 License

This project is for educational and research purposes. Please comply with website terms of service and applicable laws when scraping.

---

## 🙏 Acknowledgments

- Built with Playwright for reliable browser automation
- PostgreSQL for robust data storage  
- Prometheus & Grafana for professional monitoring
- Docker for easy development environment setup

**Happy Scraping! 🛒📊**