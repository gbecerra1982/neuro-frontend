#!/bin/bash
# Azure App Service Production Startup Script
# Automatically detects and uses the appropriate worker class

echo "=================================================="
echo "Azure Speech Live Voice with Avatar Server"
echo "Production Startup Script"
echo "=================================================="

# Set production environment
export FLASK_ENV=production
export PYTHONUNBUFFERED=1

# Disable Application Insights to avoid DNS resolution errors
export APPLICATIONINSIGHTS_CONNECTION_STRING=""
export APPINSIGHTS_INSTRUMENTATIONKEY=""
export DISABLE_APPINSIGHTS=true

# Check if eventlet is installed
if python -c "import eventlet" 2>/dev/null; then
    echo "Eventlet detected - using eventlet worker class"
    export SOCKETIO_ASYNC_MODE=eventlet
    WORKER_CLASS="eventlet"
elif python -c "import gevent" 2>/dev/null; then
    echo "Gevent detected - using gevent worker class"
    export SOCKETIO_ASYNC_MODE=gevent
    WORKER_CLASS="gevent"
else
    echo "No async library found - using gthread worker class"
    export SOCKETIO_ASYNC_MODE=threading
    WORKER_CLASS="gthread"
fi

echo "Starting Gunicorn with $WORKER_CLASS workers..."
echo "Socket.IO async mode: $SOCKETIO_ASYNC_MODE"

# Start Gunicorn with appropriate worker class
if [ "$WORKER_CLASS" = "gthread" ]; then
    # Threading mode requires threads parameter
    gunicorn --bind=0.0.0.0:8000 \
             --timeout 600 \
             --workers 2 \
             --threads 4 \
             --worker-class gthread \
             --log-level warning \
             --access-logfile - \
             --error-logfile - \
             --preload \
             app:app
else
    # Eventlet/Gevent mode
    gunicorn --bind=0.0.0.0:8000 \
             --timeout 600 \
             --workers 2 \
             --worker-class $WORKER_CLASS \
             --log-level warning \
             --access-logfile - \
             --error-logfile - \
             --preload \
             app:app
fi