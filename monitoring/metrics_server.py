"""
HTTP server for exposing Prometheus metrics
Provides health checks and metrics endpoints
"""

import logging
import threading
from typing import Optional
from flask import Flask, Response, jsonify

from monitoring.metrics import ScrapingMetrics, get_metrics_instance

logger = logging.getLogger(__name__)


class MetricsServer:
    """HTTP server for metrics and health endpoints"""
    
    def __init__(self, host: str = '0.0.0.0', port: int = 8080, 
                 metrics: ScrapingMetrics = None):
        """
        Initialize metrics server
        
        Args:
            host: Server host
            port: Server port
            metrics: ScrapingMetrics instance
        """
        self.host = host
        self.port = port
        self.metrics = metrics or get_metrics_instance()
        
        # Create Flask app
        self.app = Flask(__name__)
        self.app.logger.setLevel(logging.WARNING)  # Reduce Flask logging noise
        
        # Setup routes
        self._setup_routes()
        
        # Server thread
        self.server_thread = None
        self.running = False
        
        logger.info(f"Metrics server initialized on {host}:{port}")
    
    def _setup_routes(self):
        """Setup HTTP routes"""
        
        @self.app.route('/metrics')
        def metrics():
            """Prometheus metrics endpoint"""
            try:
                if self.metrics:
                    metrics_data = self.metrics.export_metrics()
                    return Response(
                        metrics_data,
                        mimetype='text/plain; version=0.0.4; charset=utf-8'
                    )
                else:
                    return Response(
                        '# No metrics available\n',
                        mimetype='text/plain; version=0.0.4; charset=utf-8'
                    ), 503
            except Exception as e:
                logger.error(f"Error generating metrics: {e}")
                return Response(
                    f'# Error generating metrics: {e}\n',
                    mimetype='text/plain; version=0.0.4; charset=utf-8'
                ), 500
        
        @self.app.route('/health')
        def health():
            """Health check endpoint"""
            try:
                if self.metrics:
                    return jsonify({
                        'status': 'healthy',
                        'timestamp': self.metrics.app_start_time,
                        'uptime_seconds': self.metrics.uptime_seconds._value._value if hasattr(self.metrics.uptime_seconds, '_value') else 0
                    })
                else:
                    return jsonify({
                        'status': 'degraded',
                        'message': 'No metrics instance available'
                    }), 503
            except Exception as e:
                logger.error(f"Error in health check: {e}")
                return jsonify({
                    'status': 'unhealthy',
                    'error': str(e)
                }), 500
        
        @self.app.route('/proxy-health')
        def proxy_health():
            """Proxy health summary endpoint"""
            try:
                if self.metrics:
                    proxy_health = self.metrics.get_proxy_health_summary()
                    return jsonify(proxy_health)
                else:
                    return jsonify({}), 503
            except Exception as e:
                logger.error(f"Error getting proxy health: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/metrics-summary')
        def metrics_summary():
            """Human-readable metrics summary"""
            try:
                if self.metrics:
                    summary = self.metrics.get_metrics_summary()
                    return jsonify(summary)
                else:
                    return jsonify({'error': 'No metrics available'}), 503
            except Exception as e:
                logger.error(f"Error getting metrics summary: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/')
        def root():
            """Root endpoint with links to other endpoints"""
            return jsonify({
                'service': 'Amazon Scraper Metrics',
                'endpoints': {
                    'metrics': '/metrics',
                    'health': '/health',
                    'proxy_health': '/proxy-health',
                    'summary': '/metrics-summary'
                }
            })
    
    def start(self):
        """Start the metrics server in a separate thread"""
        if self.running:
            logger.warning("Metrics server already running")
            return
        
        def run_server():
            try:
                # Disable Flask development server warning
                import werkzeug
                werkzeug.serving.run_simple(
                    self.host, 
                    self.port, 
                    self.app, 
                    use_reloader=False,
                    use_debugger=False,
                    threaded=True
                )
            except Exception as e:
                logger.error(f"Metrics server error: {e}")
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.running = True
        
        logger.info(f"Metrics server started on http://{self.host}:{self.port}")
    
    def stop(self):
        """Stop the metrics server"""
        if not self.running:
            return
        
        # Note: werkzeug development server doesn't have a clean shutdown method
        # In production, you'd use a proper WSGI server like gunicorn
        self.running = False
        logger.info("Metrics server stop requested")


def start_metrics_server(host: str = '0.0.0.0', port: int = 8080, 
                        metrics: ScrapingMetrics = None) -> MetricsServer:
    """
    Start metrics server
    
    Args:
        host: Server host
        port: Server port
        metrics: ScrapingMetrics instance
        
    Returns:
        MetricsServer instance
    """
    server = MetricsServer(host=host, port=port, metrics=metrics)
    server.start()
    return server


if __name__ == '__main__':
    # Example usage
    from monitoring.metrics import init_metrics
    
    # Initialize metrics
    metrics = init_metrics()
    
    # Start server
    server = start_metrics_server(metrics=metrics)
    
    # Keep running
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("\nMetrics server stopped")
