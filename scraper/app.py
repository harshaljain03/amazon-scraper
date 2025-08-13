from fastapi import FastAPI
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from prometheus_client import Counter, generate_latest
from fastapi.responses import PlainTextResponse

# Load env variables
from dotenv import load_dotenv
load_dotenv()

DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")

# Prometheus metric
health_checks = Counter("scraper_health_checks_total", "Number of health checks")

# FastAPI app
app = FastAPI()

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        cursor_factory=RealDictCursor
    )

@app.get("/health")
def health_check():
    health_checks.inc()
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}

@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return generate_latest()
