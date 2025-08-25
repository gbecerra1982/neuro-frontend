import logging.config
import os

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '%(asctime)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'json': {
            'format': '{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "file": "%(filename)s", "line": %(lineno)d, "message": "%(message)s"}',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'stream': 'ext://sys.stdout'
        },
        'file_debug': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': 'logs/debug.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5
        },
        'file_error': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'ERROR',
            'formatter': 'detailed',
            'filename': 'logs/error.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5
        },
        'file_performance': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': 'json',
            'filename': 'logs/performance.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5
        }
    },
    'loggers': {
        'azure_speech_proxy': {
            'level': 'DEBUG',
            'handlers': ['console', 'file_debug'],
            'propagate': False
        },
        'azure_speech_proxy.requests': {
            'level': 'DEBUG',
            'handlers': ['file_debug'],
            'propagate': False
        },
        'azure_speech_proxy.responses': {
            'level': 'DEBUG',
            'handlers': ['file_debug'],
            'propagate': False
        },
        'azure_speech_proxy.errors': {
            'level': 'ERROR',
            'handlers': ['console', 'file_error'],
            'propagate': False
        },
        'azure_speech_proxy.performance': {
            'level': 'INFO',
            'handlers': ['file_performance'],
            'propagate': False
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console', 'file_debug']
    }
}

def setup_logging():
    """Setup logging configuration"""
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Apply configuration
    logging.config.dictConfig(LOGGING_CONFIG)