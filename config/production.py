"""
Production configuration settings for YPF Neuro-Frontend
"""

import os
from datetime import timedelta

class ProductionConfig:
    """Production configuration"""
    
    # Flask Configuration
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SESSION_SECRET') or os.urandom(24).hex()
    
    # Session Configuration
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    SESSION_COOKIE_SECURE = True  # Only send cookies over HTTPS
    SESSION_COOKIE_HTTPONLY = True  # Prevent XSS attacks
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Security Headers
    SECURITY_HEADERS = {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'microphone=(self), camera=(self)'
    }
    
    # CORS Configuration
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')
    CORS_ALLOW_CREDENTIALS = True
    CORS_EXPOSE_HEADERS = ['Content-Type', 'X-Request-Id']
    CORS_ALLOW_HEADERS = ['Content-Type', 'X-Requested-With', 'Authorization']
    
    # Rate Limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "100 per minute"
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    
    # Logging Configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'WARNING')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT', 'true').lower() == 'true'
    
    # Azure OpenAI Configuration
    AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT')
    AZURE_OPENAI_API_KEY = os.environ.get('AZURE_OPENAI_API_KEY')
    AZURE_OPENAI_DEPLOYMENT = os.environ.get('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o-realtime-preview')
    AZURE_OPENAI_API_VERSION = os.environ.get('AZURE_OPENAI_API_VERSION', '2024-10-01-preview')
    
    # Backend Integration
    FASTAPI_URL = os.environ.get('FASTAPI_URL', 'http://localhost:8000/ask')
    REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 120))
    
    # Performance
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max file upload
    SEND_FILE_MAX_AGE_DEFAULT = 43200  # 12 hours cache for static files
    
    # Database Connection Pooling
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'max_overflow': 20
    }
    
    # WebSocket Configuration
    SOCKETIO_PING_TIMEOUT = int(os.environ.get('SOCKETIO_PING_TIMEOUT', 20))
    SOCKETIO_PING_INTERVAL = int(os.environ.get('SOCKETIO_PING_INTERVAL', 10))
    SOCKETIO_MAX_BUFFER_SIZE = int(os.environ.get('SOCKETIO_MAX_BUFFER_SIZE', 1000000))
    SOCKETIO_ASYNC_MODE = 'eventlet'  # For production with gunicorn
    
    # Health Check
    HEALTH_CHECK_ENABLED = True
    HEALTH_CHECK_PATH = '/health'
    
    @staticmethod
    def init_app(app):
        """Initialize application with production settings"""
        # Add security headers to all responses
        @app.after_request
        def add_security_headers(response):
            for header, value in ProductionConfig.SECURITY_HEADERS.items():
                response.headers[header] = value
            return response
        
        # Error logging
        if not app.debug and not app.testing:
            import logging
            from logging.handlers import RotatingFileHandler
            
            if not os.path.exists('logs'):
                os.mkdir('logs')
            
            file_handler = RotatingFileHandler(
                'logs/production.log',
                maxBytes=10485760,  # 10MB
                backupCount=10
            )
            file_handler.setFormatter(logging.Formatter(ProductionConfig.LOG_FORMAT))
            file_handler.setLevel(getattr(logging, ProductionConfig.LOG_LEVEL.upper()))
            app.logger.addHandler(file_handler)
            
            app.logger.setLevel(getattr(logging, ProductionConfig.LOG_LEVEL.upper()))
            app.logger.info('YPF Neuro-Frontend startup in production mode')