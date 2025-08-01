from prometheus_client import start_http_server, Counter
import time

# Create a test metric
test_counter = Counter('test_requests_total', 'Test counter')

# Start server
print("Starting metrics server...")
start_http_server(8000)
print("Metrics server started at http://localhost:8000/metrics")

# Increment counter periodically
try:
    while True:
        test_counter.inc()
        print(f"Counter incremented. Check http://localhost:8000/metrics")
        time.sleep(5)
except KeyboardInterrupt:
    print("Stopping server...")
