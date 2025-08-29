"""
Enhanced health check module for production monitoring
"""

import os
import time
import json
import psutil
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional

class HealthChecker:
    """Production health check utilities"""
    
    def __init__(self, app=None):
        self.app = app
        self.start_time = time.time()
        self.checks_performed = 0
        self.last_check_time = None
        self.cached_status = None
        self.cache_duration = 30  # Cache health status for 30 seconds
        
    def get_system_health(self) -> Dict[str, Any]:
        """Get system resource utilization"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'cpu': {
                    'usage_percent': cpu_percent,
                    'cores': psutil.cpu_count(),
                    'status': 'healthy' if cpu_percent < 80 else 'warning' if cpu_percent < 95 else 'critical'
                },
                'memory': {
                    'usage_percent': memory.percent,
                    'available_gb': round(memory.available / (1024**3), 2),
                    'total_gb': round(memory.total / (1024**3), 2),
                    'status': 'healthy' if memory.percent < 80 else 'warning' if memory.percent < 95 else 'critical'
                },
                'disk': {
                    'usage_percent': disk.percent,
                    'free_gb': round(disk.free / (1024**3), 2),
                    'total_gb': round(disk.total / (1024**3), 2),
                    'status': 'healthy' if disk.percent < 80 else 'warning' if disk.percent < 95 else 'critical'
                }
            }
        except Exception as e:
            return {
                'error': str(e),
                'status': 'error'
            }
    
    async def check_azure_openai(self) -> Dict[str, Any]:
        """Check Azure OpenAI connectivity"""
        endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')
        api_key = os.environ.get('AZURE_OPENAI_API_KEY')
        
        if not endpoint or not api_key:
            return {
                'status': 'unconfigured',
                'message': 'Azure OpenAI credentials not configured'
            }
        
        try:
            # Simple connectivity test
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    f"{endpoint}/openai/deployments?api-version=2024-10-01",
                    headers={'api-key': api_key}
                )
                
                return {
                    'status': 'healthy' if response.status_code < 400 else 'unhealthy',
                    'response_time_ms': round(response.elapsed.total_seconds() * 1000, 2),
                    'status_code': response.status_code
                }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def check_backend(self) -> Dict[str, Any]:
        """Check backend FastAPI connectivity"""
        fastapi_url = os.environ.get('FASTAPI_URL', 'http://localhost:8000/ask')
        base_url = fastapi_url.replace('/ask', '')
        
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{base_url}/health")
                
                return {
                    'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                    'response_time_ms': round(response.elapsed.total_seconds() * 1000, 2),
                    'status_code': response.status_code
                }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'url': f"{base_url}/health"
            }
    
    async def check_speech_service(self) -> Dict[str, Any]:
        """Check Azure Speech Service"""
        speech_key = os.environ.get('SPEECH_KEY')
        speech_region = os.environ.get('SPEECH_REGION')
        
        if not speech_key or not speech_region:
            return {
                'status': 'unconfigured',
                'message': 'Speech Service credentials not configured'
            }
        
        try:
            token_endpoint = f"https://{speech_region}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
            
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.post(
                    token_endpoint,
                    headers={'Ocp-Apim-Subscription-Key': speech_key}
                )
                
                return {
                    'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                    'response_time_ms': round(response.elapsed.total_seconds() * 1000, 2),
                    'region': speech_region
                }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def get_complete_health(self) -> Dict[str, Any]:
        """Get complete health status"""
        # Check cache
        current_time = time.time()
        if self.cached_status and self.last_check_time:
            if current_time - self.last_check_time < self.cache_duration:
                return self.cached_status
        
        # Perform health checks
        self.checks_performed += 1
        uptime_seconds = current_time - self.start_time
        
        # Run async checks concurrently
        azure_check, backend_check, speech_check = await asyncio.gather(
            self.check_azure_openai(),
            self.check_backend(),
            self.check_speech_service()
        )
        
        # Get system health
        system_health = self.get_system_health()
        
        # Determine overall status
        statuses = [
            azure_check.get('status', 'unknown'),
            backend_check.get('status', 'unknown'),
            speech_check.get('status', 'unknown'),
            system_health.get('cpu', {}).get('status', 'unknown'),
            system_health.get('memory', {}).get('status', 'unknown')
        ]
        
        if all(s == 'healthy' for s in statuses):
            overall_status = 'healthy'
        elif any(s in ['error', 'critical'] for s in statuses):
            overall_status = 'unhealthy'
        elif any(s == 'warning' for s in statuses):
            overall_status = 'degraded'
        else:
            overall_status = 'unknown'
        
        health_status = {
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'uptime': {
                'seconds': round(uptime_seconds),
                'human_readable': self._format_uptime(uptime_seconds)
            },
            'checks_performed': self.checks_performed,
            'version': os.environ.get('APP_VERSION', '2.1.0'),
            'environment': os.environ.get('NODE_ENV', 'production'),
            'components': {
                'azure_openai': azure_check,
                'backend_api': backend_check,
                'speech_service': speech_check,
                'system': system_health
            }
        }
        
        # Cache the result
        self.cached_status = health_status
        self.last_check_time = current_time
        
        return health_status
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        days, remainder = divmod(int(seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        
        return " ".join(parts)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get application metrics"""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'uptime_seconds': round(time.time() - self.start_time),
            'health_checks_performed': self.checks_performed,
            'last_check_time': self.last_check_time,
            'cache_hit_rate': self._calculate_cache_hit_rate()
        }
    
    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate for health checks"""
        # This is a simplified implementation
        # In production, you'd track actual hits vs misses
        if self.checks_performed > 0:
            return round((self.checks_performed - 1) / self.checks_performed * 100, 2)
        return 0.0

# Global health checker instance
health_checker = HealthChecker()