import uvicorn
import logging
import sys
import os
import traceback
from datetime import datetime
import json
import time
from api.main import app

# ===== CONFIGURACIÓN DE LOGGING EXHAUSTIVO =====
# Crear directorio de logs si no existe
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
    print(f"📁 Directorio de logs creado: {log_dir}")

# Configurar formato de logging con máximo detalle
detailed_format = (
    "%(asctime)s.%(msecs)03d | PID:%(process)d | Thread:%(thread)d | "
    "%(levelname)-8s | %(name)-25s | %(filename)s:%(lineno)d | "
    "%(funcName)s | %(message)s"
)

# Configurar handlers para diferentes archivos de log
file_handler_all = logging.FileHandler(
    f'{log_dir}/backend_all_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    encoding='utf-8'
)
file_handler_all.setFormatter(logging.Formatter(detailed_format, datefmt='%Y-%m-%d %H:%M:%S'))

file_handler_errors = logging.FileHandler(
    f'{log_dir}/backend_errors_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
    encoding='utf-8'
)
file_handler_errors.setLevel(logging.ERROR)
file_handler_errors.setFormatter(logging.Formatter(detailed_format, datefmt='%Y-%m-%d %H:%M:%S'))

# Console handler con colores
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(detailed_format, datefmt='%Y-%m-%d %H:%M:%S'))

# Configurar root logger
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler_all, file_handler_errors, console_handler]
)

# Crear logger específico para backend
logger = logging.getLogger("backend")
logger.setLevel(logging.DEBUG)

# Configurar loggers de bibliotecas específicas
loggers_config = {
    "uvicorn": logging.DEBUG,
    "uvicorn.error": logging.DEBUG,
    "uvicorn.access": logging.DEBUG,
    "fastapi": logging.DEBUG,
    "langchain": logging.DEBUG,
    "langchain.chains": logging.DEBUG,
    "langchain.agents": logging.DEBUG,
    "httpx": logging.DEBUG,
    "httpcore": logging.DEBUG,
    "asyncio": logging.DEBUG,
    "api": logging.DEBUG,
    "agents": logging.DEBUG,
    "services": logging.DEBUG,
    "tools": logging.DEBUG,
    "workflows": logging.DEBUG
}

for logger_name, level in loggers_config.items():
    lib_logger = logging.getLogger(logger_name)
    lib_logger.setLevel(level)
    logger.debug(f"Logger configurado: {logger_name} -> {logging.getLevelName(level)}")

# ===== INFORMACIÓN DEL SISTEMA =====
def log_system_info():
    """Log información detallada del sistema al inicio"""
    logger.info("="*80)
    logger.info("🚀 INICIANDO BACKEND NEURO RAG")
    logger.info("="*80)
    
    system_info = {
        "timestamp": datetime.now().isoformat(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": sys.platform,
        "cwd": os.getcwd(),
        "pid": os.getpid(),
        "environment": {
            "PYTHONPATH": os.environ.get("PYTHONPATH", "Not set"),
            "PATH": os.environ.get("PATH", "Not set")[:200] + "...",
            "USER": os.environ.get("USER", os.environ.get("USERNAME", "Unknown")),
            "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", "Not in venv")
        },
        "python_path": sys.path[:5],  # Primeros 5 paths
        "installed_packages": []
    }
    
    # Listar paquetes importantes instalados
    try:
        import pkg_resources
        important_packages = ["fastapi", "uvicorn", "langchain", "langchain-core", "pydantic"]
        for package in important_packages:
            try:
                version = pkg_resources.get_distribution(package).version
                system_info["installed_packages"].append(f"{package}=={version}")
            except:
                system_info["installed_packages"].append(f"{package}==Not installed")
    except ImportError:
        logger.warning("pkg_resources no disponible para listar paquetes")
    
    logger.info(f"Información del sistema:\n{json.dumps(system_info, indent=2, ensure_ascii=False)}")
    logger.info("="*80)

def run_api(host: str = "0.0.0.0", port: int = 8000, debug: bool = False):
    """
    Ejecutar la API con logging exhaustivo
    
    Args:
        host: Host donde correr el servidor
        port: Puerto donde correr el servidor  
        debug: Si activar modo debug con auto-reload
    """
    start_time = time.time()
    
    try:
        # Log información del sistema
        log_system_info()
        
        logger.info(f"📌 Configuración del servidor:")
        logger.info(f"   Host: {host}")
        logger.info(f"   Port: {port}")
        logger.info(f"   Debug Mode: {debug}")
        logger.info(f"   Auto-reload: {debug}")
        logger.info(f"   Log Level: DEBUG")
        logger.info(f"   Log Files: {log_dir}/")
        
        # Verificar si el puerto está disponible
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            logger.warning(f"⚠️ El puerto {port} ya está en uso. El servidor podría fallar al iniciar.")
        else:
            logger.info(f"✅ Puerto {port} está disponible")
        
        logger.info("="*80)
        logger.info(f"🌐 Iniciando servidor Uvicorn...")
        logger.info(f"📍 URL del servidor: http://{host}:{port}")
        logger.info(f"📍 Documentación API: http://{host}:{port}/docs")
        logger.info(f"📍 OpenAPI Schema: http://{host}:{port}/openapi.json")
        logger.info("="*80)
        
        # Configuración de Uvicorn con logging máximo
        uvicorn_config = {
            "app": "api.main:app",
            "host": host,
            "port": port,
            "reload": debug,
            "log_level": "debug",  # Máximo nivel de log
            "access_log": True,     # Habilitar access log
            "use_colors": True,     # Colores en consola
            "reload_dirs": ["src"] if debug else None,  # Directorios a monitorear
            "reload_delay": 0.25 if debug else None,    # Delay para reload
            "server_header": True,  # Incluir header del servidor
            "date_header": True,    # Incluir fecha en headers
            "log_config": {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "format": detailed_format,
                        "datefmt": "%Y-%m-%d %H:%M:%S"
                    },
                    "access": {
                        "format": '%(asctime)s | ACCESS | %(message)s',
                        "datefmt": "%Y-%m-%d %H:%M:%S"
                    }
                },
                "handlers": {
                    "default": {
                        "formatter": "default",
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stdout"
                    },
                    "access": {
                        "formatter": "access",
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stdout"
                    },
                    "file": {
                        "formatter": "default",
                        "class": "logging.FileHandler",
                        "filename": f"{log_dir}/uvicorn_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                        "encoding": "utf-8"
                    }
                },
                "loggers": {
                    "uvicorn": {
                        "handlers": ["default", "file"],
                        "level": "DEBUG",
                        "propagate": False
                    },
                    "uvicorn.error": {
                        "handlers": ["default", "file"],
                        "level": "DEBUG",
                        "propagate": False
                    },
                    "uvicorn.access": {
                        "handlers": ["access", "file"],
                        "level": "DEBUG",
                        "propagate": False
                    }
                }
            }
        }
        
        # Log configuración final
        logger.debug(f"Configuración Uvicorn completa:\n{json.dumps({k: str(v) for k, v in uvicorn_config.items() if k != 'log_config'}, indent=2)}")
        
        # Ejecutar servidor
        uvicorn.run(**uvicorn_config)
        
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        logger.info("="*80)
        logger.info(f"⏹️ Servidor detenido por el usuario")
        logger.info(f"⏱️ Tiempo de ejecución: {elapsed:.2f} segundos")
        logger.info("="*80)
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("="*80)
        logger.error(f"❌ ERROR CRÍTICO al ejecutar el servidor")
        logger.error(f"Tipo de error: {type(e).__name__}")
        logger.error(f"Mensaje: {str(e)}")
        logger.error(f"Stack trace completo:\n{traceback.format_exc()}")
        logger.error(f"⏱️ Tiempo antes del error: {elapsed:.2f} segundos")
        logger.error("="*80)
        
        # Re-lanzar la excepción
        raise
    
    finally:
        logger.info("🔚 Finalizando proceso backend.py")
        logger.info("="*80)

if __name__ == "__main__":
    logger.info("🎯 Ejecutando backend.py como script principal")
    
    # Parsear argumentos de línea de comandos si es necesario
    import argparse
    parser = argparse.ArgumentParser(description="Backend Server para Neuro RAG")
    parser.add_argument("--host", default="0.0.0.0", help="Host del servidor")
    parser.add_argument("--port", type=int, default=8000, help="Puerto del servidor")
    parser.add_argument("--debug", action="store_true", help="Activar modo debug")
    parser.add_argument("--no-reload", action="store_true", help="Desactivar auto-reload incluso en debug")
    
    args = parser.parse_args()
    
    # Override reload si se especifica --no-reload
    debug_mode = args.debug and not args.no_reload
    
    logger.info(f"Argumentos de línea de comandos: {vars(args)}")
    
    try:
        run_api(host=args.host, port=args.port, debug=debug_mode)
    except Exception as e:
        logger.critical(f"💥 Fallo catastrófico: {e}")
        sys.exit(1)
