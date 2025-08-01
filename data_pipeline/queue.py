import redis
import json
import os
from dotenv import load_dotenv

load_dotenv()

class QueueManager:
    def __init__(self):
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url)
        self.queue_name = 'scraping_jobs'
        self.results_queue = 'scraping_results'
    
    def add_job(self, job_data):
        """Add a scraping job to the queue"""
        try:
            job_json = json.dumps(job_data)
            self.redis_client.lpush(self.queue_name, job_json)
            print(f"Added job to queue: {job_data.get('url', 'Unknown URL')}")
            return True
        except Exception as e:
            print(f"Error adding job to queue: {e}")
            return False
    
    def get_job(self, timeout=10):
        """Get next job from queue (blocking)"""
        try:
            result = self.redis_client.brpop(self.queue_name, timeout=timeout)
            if result:
                job_json = result[1].decode('utf-8')
                return json.loads(job_json)
            return None
        except Exception as e:
            print(f"Error getting job from queue: {e}")
            return None
    
    def add_result(self, result_data):
        """Add scraping result to results queue"""
        try:
            result_json = json.dumps(result_data, default=str)
            self.redis_client.lpush(self.results_queue, result_json)
            return True
        except Exception as e:
            print(f"Error adding result to queue: {e}")
            return False
    
    def get_queue_size(self):
        """Get number of jobs in queue"""
        return self.redis_client.llen(self.queue_name)
    
    def clear_queue(self):
        """Clear all jobs from queue"""
        self.redis_client.delete(self.queue_name)
        print("Queue cleared")
