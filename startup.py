#!/usr/bin/env python
"""
Production startup script for YPF Neuro-Frontend
Uses Gunicorn with eventlet worker for Socket.IO support
"""

import os
import sys
import multiprocessing
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Production configuration
bind = f"{os.environ.get('FLASK_HOST', '0.0.0.0')}:{os.environ.get('FLASK_PORT', '5000')}"
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'eventlet'  # Required for Socket.IO
worker_connections = int(os.environ.get('WORKER_CONNECTIONS', 1000))
threads = int(os.environ.get('GUNICORN_THREADS', 2))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', 5))

# Logging
accesslog = os.environ.get('ACCESS_LOG', '-')
errorlog = os.environ.get('ERROR_LOG', '-')
loglevel = os.environ.get('LOG_LEVEL', 'info').lower()

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Performance
preload_app = True
max_requests = int(os.environ.get('MAX_REQUESTS', 1000))
max_requests_jitter = int(os.environ.get('MAX_REQUESTS_JITTER', 50))

# Application
wsgi_app = "app:app"

def when_ready(server):
    """Called just after the server is started"""
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT"""
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked"""
    server.log.info(f"Forking worker {worker.pid}")

def post_fork(server, worker):
    """Called just after a worker has been forked"""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal"""
    worker.log.info("Worker received SIGABRT signal")

if __name__ == "__main__":
    # For direct execution, use gunicorn command
    print("Use: gunicorn -c startup.py app:app")
    print("Or for development: python app.py")