"""
Apache Airflow DAG for Amazon Scraper
Schedules hourly scraping jobs with monitoring and alerting
"""

from datetime import datetime, timedelta
from typing import Dict, Any

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.sensors.filesystem import FileSensor
from airflow.models import Variable
from airflow.utils.dates import days_ago
from airflow.exceptions import AirflowException

# Default arguments for the DAG
default_args = {
    'owner': 'amazon_scraper',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=15),
    'catchup': False,
}

# DAG definition
dag = DAG(
    dag_id='amazon_scraper_hourly',
    default_args=default_args,
    description='Hourly Amazon product scraping with monitoring',
    schedule_interval='@hourly',  # Run every hour
    max_active_runs=1,  # Only one instance running at a time
    tags=['amazon', 'scraper', 'ecommerce'],
    doc_md="""
    # Amazon Scraper DAG
    
    This DAG orchestrates hourly Amazon product scraping with the following features:
    - Automated product data collection
    - Error handling and retry logic
    - Performance monitoring
    - Data quality checks
    - Alerting on failures
    
    ## Dependencies
    - PostgreSQL database
    - Redis cache
    - Proxy configuration
    - 2Captcha API (optional)
    """,
)


def check_scraper_health(**context) -> bool:
    """
    Check if scraper service is healthy before starting
    
    Returns:
        bool: True if healthy, raises exception otherwise
    """
    import requests
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Check metrics endpoint
        response = requests.get('http://localhost:8080/health', timeout=10)
        
        if response.status_code == 200:
            health_data = response.json()
            
            if health_data.get('status') == 'healthy':
                logger.info("Scraper health check passed")
                return True
            else:
                raise AirflowException(f"Scraper not healthy: {health_data}")
        else:
            raise AirflowException(f"Health check failed with status {response.status_code}")
            
    except requests.RequestException as e:
        raise AirflowException(f"Health check request failed: {e}")


def parse_scraper_results(**context) -> Dict[str, Any]:
    """
    Parse scraper results and extract key metrics
    
    Returns:
        Dict with scraper statistics
    """
    import json
    import logging
    from pathlib import Path
    
    logger = logging.getLogger(__name__)
    
    # Get the task instance to access XCom
    ti = context['task_instance']
    
    # Get the output from the scraper task
    scraper_output = ti.xcom_pull(task_ids='run_scraper')
    
    if not scraper_output:
        raise AirflowException("No output from scraper task")
    
    # Parse the output (assuming it's a JSON string or similar)
    try:
        # This would depend on how your scraper outputs results
        # For now, we'll simulate parsing
        stats = {
            'products_scraped': 0,
            'success_rate': 0.0,
            'errors': 0,
            'duration_seconds': 0,
        }
        
        # Extract stats from scraper output
        if 'products_found' in str(scraper_output):
            # Simple parsing - in practice you'd use more sophisticated parsing
            import re
            matches = re.findall(r'products_found[:\s]+(\d+)', str(scraper_output))
            if matches:
                stats['products_scraped'] = int(matches[0])
        
        logger.info(f"Parsed scraper stats: {stats}")
        
        # Store stats for downstream tasks
        ti.xcom_push(key='scraper_stats', value=stats)
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to parse scraper results: {e}")
        raise AirflowException(f"Result parsing failed: {e}")


def validate_data_quality(**context) -> bool:
    """
    Validate the quality of scraped data
    
    Returns:
        bool: True if data quality is acceptable
    """
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Get stats from previous task
    ti = context['task_instance']
    stats = ti.xcom_pull(key='scraper_stats')
    
    if not stats:
        raise AirflowException("No statistics available for quality check")
    
    # Define quality thresholds
    min_products = int(Variable.get("min_products_per_run", default_var=10))
    min_success_rate = float(Variable.get("min_success_rate", default_var=0.8))
    
    products_scraped = stats.get('products_scraped', 0)
    success_rate = stats.get('success_rate', 0.0)
    
    # Validate thresholds
    if products_scraped < min_products:
        logger.warning(f"Low product count: {products_scraped} < {min_products}")
        # Don't fail the DAG for low counts, just warn
    
    if success_rate < min_success_rate:
        raise AirflowException(
            f"Success rate too low: {success_rate} < {min_success_rate}"
        )
    
    logger.info(f"Data quality check passed: {products_scraped} products, {success_rate} success rate")
    return True


# Task definitions

# 1. Health check task
health_check = PythonOperator(
    task_id='check_scraper_health',
    python_callable=check_scraper_health,
    dag=dag,
    doc_md="Check if scraper service is healthy before starting",
)

# 2. Main scraper task
run_scraper = BashOperator(
    task_id='run_scraper',
    bash_command="""
    cd /opt/airflow/dags/amazon-scraper && \
    python -m scheduler.scheduler
    """,
    dag=dag,
    doc_md="Execute the main scraper job",
    retries=1,
    retry_delay=timedelta(minutes=10),
)

# 3. Parse results task
parse_results = PythonOperator(
    task_id='parse_scraper_results',
    python_callable=parse_scraper_results,
    dag=dag,
    doc_md="Parse scraper output and extract metrics",
)

# 4. Data quality validation
validate_quality = PythonOperator(
    task_id='validate_data_quality',
    python_callable=validate_data_quality,
    dag=dag,
    doc_md="Validate the quality of scraped data",
)

# 5. Cleanup task
cleanup = BashOperator(
    task_id='cleanup_temp_files',
    bash_command="""
    # Clean up temporary files
    find /tmp -name "scraper_*" -type f -mtime +1 -delete || true
    
    # Clean up old logs
    find /opt/airflow/logs -name "*.log" -mtime +7 -delete || true
    
    echo "Cleanup completed"
    """,
    dag=dag,
    doc_md="Clean up temporary files and old logs",
    trigger_rule='all_done',  # Run regardless of upstream success/failure
)

# 6. Success notification
success_notification = EmailOperator(
    task_id='send_success_notification',
    to=['admin@company.com'],
    subject='Amazon Scraper - Success',
    html_content="""
    <h3>Amazon Scraper Job Completed Successfully</h3>
    <p><strong>Execution Date:</strong> {{ ds }}</p>
    <p><strong>DAG Run ID:</strong> {{ dag_run.run_id }}</p>
    <p><strong>Products Scraped:</strong> {{ task_instance.xcom_pull(key='scraper_stats')['products_scraped'] if task_instance.xcom_pull(key='scraper_stats') else 'N/A' }}</p>
    <p><strong>Duration:</strong> {{ task_instance.xcom_pull(key='scraper_stats')['duration_seconds'] if task_instance.xcom_pull(key='scraper_stats') else 'N/A' }} seconds</p>
    
    <p>Check the <a href="http://localhost:8080/metrics">metrics dashboard</a> for detailed statistics.</p>
    """,
    dag=dag,
    trigger_rule='all_success',
)

# 7. Failure notification
failure_notification = EmailOperator(
    task_id='send_failure_notification',
    to=['admin@company.com', 'dev-team@company.com'],
    subject='Amazon Scraper - FAILURE',
    html_content="""
    <h3 style="color: red;">Amazon Scraper Job Failed</h3>
    <p><strong>Execution Date:</strong> {{ ds }}</p>
    <p><strong>DAG Run ID:</strong> {{ dag_run.run_id }}</p>
    <p><strong>Failed Task:</strong> {{ task_instance.task_id }}</p>
    
    <p><strong>Error Details:</strong></p>
    <pre>{{ task_instance.log_url }}</pre>
    
    <p>Please investigate and resolve the issue.</p>
    <p>Check the <a href="http://localhost:8080/health">health endpoint</a> and <a href="http://localhost:3000">Grafana dashboard</a>.</p>
    """,
    dag=dag,
    trigger_rule='one_failed',
)

# Task dependencies
health_check >> run_scraper >> parse_results >> validate_quality

# Parallel cleanup and notifications
validate_quality >> [success_notification, cleanup]
run_scraper >> failure_notification

# Alternative: File sensor for configuration changes
config_sensor = FileSensor(
    task_id='wait_for_config_update',
    filepath='/opt/airflow/dags/amazon-scraper/config/proxies.json',
    fs_conn_id='fs_default',
    dag=dag,
    poke_interval=60,  # Check every minute
    timeout=300,  # Wait up to 5 minutes
    mode='reschedule',  # Don't block worker
)

# Optional: Advanced monitoring with custom metrics
def publish_metrics(**context):
    """
    Publish custom metrics to external monitoring system
    """
    import requests
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    
    ti = context['task_instance']
    stats = ti.xcom_pull(key='scraper_stats')
    
    if not stats:
        logger.warning("No statistics to publish")
        return
    
    # Example: Send to external monitoring service
    metrics_payload = {
        'timestamp': context['execution_date'].isoformat(),
        'dag_id': dag.dag_id,
        'run_id': context['dag_run'].run_id,
        'metrics': stats,
    }
    
    try:
        # Replace with your monitoring service endpoint
        response = requests.post(
            'http://monitoring-service/api/metrics',
            json=metrics_payload,
            timeout=30
        )
        response.raise_for_status()
        logger.info("Metrics published successfully")
        
    except requests.RequestException as e:
        logger.error(f"Failed to publish metrics: {e}")
        # Don't fail the DAG for monitoring issues

# Optional metrics publishing task
publish_custom_metrics = PythonOperator(
    task_id='publish_custom_metrics',
    python_callable=publish_metrics,
    dag=dag,
    doc_md="Publish custom metrics to external monitoring system",
    trigger_rule='all_done',
)

# Add to dependency chain
validate_quality >> publish_custom_metrics

# DAG documentation
dag.doc_md = """
## Amazon Scraper Airflow DAG

This DAG orchestrates the Amazon product scraping process with the following workflow:

1. **Health Check**: Verify scraper service is healthy
2. **Run Scraper**: Execute the main scraping job
3. **Parse Results**: Extract metrics from scraper output
4. **Validate Quality**: Check data quality thresholds
5. **Notifications**: Send success/failure emails
6. **Cleanup**: Remove temporary files
7. **Metrics**: Publish to external monitoring (optional)

### Configuration Variables

- `min_products_per_run`: Minimum products required per run (default: 10)
- `min_success_rate`: Minimum success rate threshold (default: 0.8)

### Monitoring

- Health endpoint: http://localhost:8080/health
- Metrics endpoint: http://localhost:8080/metrics
- Grafana dashboard: http://localhost:3000

### Troubleshooting

If the DAG fails:
1. Check the scraper health endpoint
2. Review task logs in Airflow UI
3. Verify proxy configuration
4. Check database connectivity
5. Validate 2Captcha API key (if used)
"""
