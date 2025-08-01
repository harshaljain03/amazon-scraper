"""
Enhanced scheduler that integrates with the main scraper
"""

import asyncio
import logging
import subprocess
import sys
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from storage.models import ScrapingSession
from monitoring.metrics import get_metrics_instance


logger = structlog.get_logger(__name__)


class SchedulerConfig:
    """Configuration for the scheduler"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL', 'sqlite:///amazon_scraper.db')
        self.metrics_enabled = os.getenv('METRICS_ENABLED', 'true').lower() == 'true'
        self.max_concurrent_jobs = int(os.getenv('MAX_CONCURRENT_JOBS', '1'))
        self.job_timeout = int(os.getenv('JOB_TIMEOUT', '3600'))  # 1 hour
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')


class ScraperScheduler:
    """
    Scheduler for Amazon scraper jobs
    Manages job execution, monitoring, and cleanup
    """
    
    def __init__(self, config: SchedulerConfig = None):
        self.config = config or SchedulerConfig()
        self.active_jobs = {}
        self.job_counter = 0
        
        # Setup database connection
        self.engine = create_engine(self.config.database_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Setup metrics if enabled
        self.metrics = get_metrics_instance() if self.config.metrics_enabled else None
    
    async def run_scraper_job(self) -> Dict[str, Any]:
        """
        Run a single scraper job
        
        Returns:
            Dictionary with job results and statistics
        """
        job_id = f"job_{self.job_counter}_{int(datetime.now().timestamp())}"
        self.job_counter += 1
        
        logger.info("Starting scraper job", job_id=job_id)
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Check if we can run another job
            if len(self.active_jobs) >= self.config.max_concurrent_jobs:
                raise Exception(f"Maximum concurrent jobs ({self.config.max_concurrent_jobs}) reached")
            
            # Mark job as active
            self.active_jobs[job_id] = {
                'start_time': start_time,
                'status': 'running'
            }
            
            # Run the main scraper
            result = await self._execute_scraper()
            
            # Mark job as completed
            self.active_jobs[job_id]['status'] = 'completed'
            self.active_jobs[job_id]['end_time'] = datetime.now(timezone.utc)
            
            logger.info("Scraper job completed successfully", 
                       job_id=job_id, 
                       duration=result.get('duration', 0))
            
            return {
                'job_id': job_id,
                'status': 'success',
                'start_time': start_time.isoformat(),
                'end_time': datetime.now(timezone.utc).isoformat(),
                'result': result
            }
            
        except Exception as e:
            # Mark job as failed
            if job_id in self.active_jobs:
                self.active_jobs[job_id]['status'] = 'failed'
                self.active_jobs[job_id]['error'] = str(e)
            
            logger.error("Scraper job failed", job_id=job_id, error=str(e))
            
            return {
                'job_id': job_id,
                'status': 'error',
                'start_time': start_time.isoformat(),
                'end_time': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }
            
        finally:
            # Clean up job from active list
            self.active_jobs.pop(job_id, None)
    
    async def _execute_scraper(self) -> Dict[str, Any]:
        """Execute the main scraper process"""
        command = [sys.executable, "-m", "scraper.main"]
        
        logger.info("Executing scraper command", command=" ".join(command))
        
        start_time = datetime.now()
        
        # Run scraper as subprocess
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd()
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=self.config.job_timeout
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            if process.returncode == 0:
                # Parse output for statistics
                stats = self._parse_scraper_output(stdout.decode())
                
                return {
                    'success': True,
                    'duration': duration,
                    'returncode': process.returncode,
                    'stats': stats,
                    'stdout': stdout.decode(),
                    'stderr': stderr.decode()
                }
            else:
                raise Exception(f"Scraper failed with return code {process.returncode}: {stderr.decode()}")
                
        except asyncio.TimeoutError:
            # Kill the process if it times out
            process.kill()
            await process.wait()
            raise Exception(f"Scraper job timed out after {self.config.job_timeout} seconds")
    
    def _parse_scraper_output(self, output: str) -> Dict[str, Any]:
        """Parse scraper output to extract statistics"""
        stats = {
            'products_found': 0,
            'products_created': 0,
            'products_updated': 0,
            'pages_scraped': 0,
            'errors': 0
        }
        
        # Simple parsing of log output
        # In a real implementation, you might use structured logging
        lines = output.split('\n')
        for line in lines:
            if 'products_found' in line.lower():
                try:
                    # Extract number from log line
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'products_found' in part.lower() and i + 1 < len(parts):
                            stats['products_found'] += int(parts[i + 1])
                except (ValueError, IndexError):
                    pass
        
        return stats
    
    def get_job_status(self) -> Dict[str, Any]:
        """Get current job status"""
        return {
            'active_jobs': len(self.active_jobs),
            'max_concurrent_jobs': self.config.max_concurrent_jobs,
            'jobs': dict(self.active_jobs)
        }
    
    async def get_recent_sessions(self, limit: int = 10) -> list[Dict[str, Any]]:
        """Get recent scraping sessions from database"""
        session = self.SessionLocal()
        try:
            sessions = session.query(ScrapingSession)\
                .order_by(ScrapingSession.started_at.desc())\
                .limit(limit)\
                .all()
            
            return [
                {
                    'session_id': s.session_id,
                    'status': s.status,
                    'started_at': s.started_at.isoformat(),
                    'ended_at': s.ended_at.isoformat() if s.ended_at else None,
                    'products_found': s.products_found,
                    'successful_scrapes': s.successful_scrapes,
                    'failed_scrapes': s.failed_scrapes
                }
                for s in sessions
            ]
        finally:
            session.close()


async def main():
    """Main scheduler entry point"""
    config = SchedulerConfig()
    scheduler = ScraperScheduler(config)
    
    logger.info("Starting scheduled scraper job")
    
    try:
        result = await scheduler.run_scraper_job()
        
        if result['status'] == 'success':
            logger.info("Scheduled job completed successfully", result=result)
            return 0
        else:
            logger.error("Scheduled job failed", result=result)
            return 1
            
    except Exception as e:
        logger.error("Scheduler failed", error=str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    import sys
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Run scheduler
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
