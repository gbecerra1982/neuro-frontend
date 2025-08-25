# ================================
# AZURE OPENAI REALTIME API BACKEND
# Production Server with Avatar Support
# ================================

from flask import Flask, render_template, Response, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import json
import uuid
import logging
from datetime import datetime
from dotenv import load_dotenv
import requests

# Import YPF minipywo system
try:
    from src.agente import minipywo_app
    from src.pywo_aux_func import replace_token
    MINIPYWO_AVAILABLE = True
except ImportError:
    MINIPYWO_AVAILABLE = False
    logging.warning("minipywo system not available - function calling will be limited")

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================================
# ENVIRONMENT VARIABLES
# ================================

# Azure OpenAI Realtime API Configuration
AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT')
AZURE_OPENAI_API_KEY = os.environ.get('AZURE_OPENAI_API_KEY')
AZURE_OPENAI_DEPLOYMENT = os.environ.get('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o-realtime-preview')
AZURE_OPENAI_API_VERSION = os.environ.get('AZURE_OPENAI_API_VERSION', '2025-04-01-preview')
AZURE_OPENAI_MODEL = os.environ.get('AZURE_OPENAI_MODEL', 'gpt-4o-realtime-preview')

# Speech Service Config
SPEECH_KEY = os.environ.get('SPEECH_KEY')
SPEECH_ENDPOINT = os.environ.get('SPEECH_ENDPOINT')
SPEECH_REGION = os.environ.get('SPEECH_REGION')

# Legacy Voice Live compatibility
AZURE_VOICE_LIVE_ENDPOINT = os.environ.get('AZURE_VOICE_LIVE_ENDPOINT', AZURE_OPENAI_ENDPOINT)
AZURE_VOICE_LIVE_API_KEY = os.environ.get('AZURE_VOICE_LIVE_API_KEY', AZURE_OPENAI_API_KEY)

# Standard Azure OpenAI for minipywo
AZURE_OPENAI_STANDARD_ENDPOINT = os.environ.get('AZURE_OPENAI_STANDARD_ENDPOINT')
AZURE_OPENAI_STANDARD_API_KEY = os.environ.get('AZURE_OPENAI_STANDARD_API_KEY')
AZURE_OPENAI_DEPLOYMENT_NAME = os.environ.get('AZURE_OPENAI_DEPLOYMENT_NAME')

# ICE/TURN Server Configuration
ICE_SERVER_URL = os.environ.get('ICE_SERVER_URL')
ICE_SERVER_USERNAME = os.environ.get('ICE_SERVER_USERNAME')
ICE_SERVER_PASSWORD = os.environ.get('ICE_SERVER_PASSWORD')

# Avatar Configuration
ENABLE_AVATAR = os.environ.get('ENABLE_AVATAR', 'true').lower() == 'true'
AVATAR_CHARACTER = os.environ.get('AVATAR_CHARACTER', 'lisa')
AVATAR_STYLE = os.environ.get('AVATAR_STYLE', 'casual-sitting')

# Voice Configuration
VOICE_NAME = os.environ.get('VOICE_NAME', 'es-AR-TomasNeural')
VOICE_MODEL = os.environ.get('VOICE_MODEL', 'alloy')
LANGUAGE = os.environ.get('LANGUAGE', 'es-AR')

# Server Configuration
FLASK_PORT = int(os.environ.get('FLASK_PORT', 5000))
FLASK_HOST = os.environ.get('FLASK_HOST', '0.0.0.0')

# ================================
# FLASK APPLICATION SETUP
# ================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', str(uuid.uuid4()))

# Configure CORS
cors_origins = os.environ.get('CORS_ORIGINS', '*').split(',')
CORS(app, origins=cors_origins)

# Configure SocketIO
socketio = SocketIO(
    app, 
    cors_allowed_origins=cors_origins,
    ping_timeout=int(os.environ.get('SOCKETIO_PING_TIMEOUT', 20)),
    ping_interval=int(os.environ.get('SOCKETIO_PING_INTERVAL', 10))
)

# ================================
# MINIPYWO SYSTEM INITIALIZATION
# ================================

if MINIPYWO_AVAILABLE:
    # YPF text corrections
    original_list = ['Rial', 'Ta', 'Taim', 'aim', 'ipf', 'IPF', 'bpe', 'BPE']
    replacement_list = ['Real', 'Ti', 'Time', 'ime', 'YPF', 'YPF', 'VPE', 'VPE']
    
    # Initialize minipywo system
    try:
        wl_pywo = minipywo_app()
        logger.info("minipywo system initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize minipywo: {e}")
        MINIPYWO_AVAILABLE = False

# ================================
# CLIENT SESSION MANAGEMENT
# ================================

client_sessions = {}

def generate_client_id():
    """Generate unique client ID"""
    return str(uuid.uuid4())

def get_or_create_session(client_id):
    """Get or create client session"""
    if client_id not in client_sessions:
        client_sessions[client_id] = {
            'id': client_id,
            'created_at': datetime.now().isoformat(),
            'messages': [],
            'metadata': {}
        }
    return client_sessions[client_id]

# ================================
# MAIN ROUTES
# ================================

@app.route("/")
def index():
    """Main interface for Azure OpenAI Realtime API"""
    client_id = generate_client_id()
    return render_template(
        "voice_live_interface.html",  # This should be your production HTML artifact
        client_id=client_id
    )

@app.route("/api/voice-live-config", methods=["GET"])
def get_voice_live_config():
    """Provide configuration for Realtime API frontend"""
    try:
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
            return jsonify({
                "error": "Azure OpenAI Realtime API not configured",
                "message": "Configure AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY"
            }), 400
        
        # Build configuration response
        config = {
            "endpoint": AZURE_OPENAI_ENDPOINT,
            "apiKey": AZURE_OPENAI_API_KEY,
            "deployment": AZURE_OPENAI_DEPLOYMENT,
            "deploymentName": AZURE_OPENAI_DEPLOYMENT,
            "apiVersion": AZURE_OPENAI_API_VERSION,
            "model": AZURE_OPENAI_MODEL,
            "status": "ready",
            "features": {
                "avatar": ENABLE_AVATAR,
                "minipywo": MINIPYWO_AVAILABLE,
                "functionCalling": True
            }
        }
        
        # Add ICE servers if available
        if ICE_SERVER_URL:
            config["turnServers"] = [{
                "urls": ICE_SERVER_URL,
                "username": ICE_SERVER_USERNAME,
                "credential": ICE_SERVER_PASSWORD
            }]
        
        # Add tools configuration if minipywo is available
        if MINIPYWO_AVAILABLE:
            config["tools"] = [{
                "type": "function",
                "name": "query_minipywo",
                "description": "Query minipywo system for YPF equipment, wells, workover, and technical data",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "User query to be processed by minipywo"
                        }
                    },
                    "required": ["query"]
                }
            }]
        
        return jsonify(config)
        
    except Exception as e:
        logger.error(f"Error getting Realtime API config: {e}")
        return jsonify({"error": str(e)}), 500

# @app.route("/api/minipywo-process", methods=["POST"])
# def api_minipywo_process():
#     """Process query with minipywo system"""
#     if not MINIPYWO_AVAILABLE:
#         return jsonify({
#             "status": "error",
#             "message": "minipywo system not available"
#         }), 503
    
#     try:
#         data = request.get_json()
#         user_message = data.get('message', '')
#         client_id = data.get('client_id', generate_client_id())
#         vad_metrics = data.get('vad_metrics', {})
        
#         logger.info(f"Processing with minipywo: {user_message}")
        
#         # Apply YPF corrections
#         corrected_message = replace_token(user_message, original_list, replacement_list)
        
#         # Configure minipywo
#         config = {"configurable": {"thread_id": client_id}}
        
#         # Process with minipywo
#         result = wl_pywo.invoke({"question": corrected_message}, config)
#         response_text = result.get("query_result", "Error processing YPF query")
        
#         # Store in session
#         session = get_or_create_session(client_id)
#         session['messages'].append({
#             'role': 'user',
#             'content': user_message,
#             'timestamp': datetime.now().isoformat()
#         })
#         session['messages'].append({
#             'role': 'assistant',
#             'content': response_text,
#             'timestamp': datetime.now().isoformat()
#         })
        
#         logger.info(f"minipywo response: {response_text[:100]}...")
        
#         return jsonify({
#             "status": "success",
#             "response": response_text,
#             "client_id": client_id,
#             "source": "minipywo_ypf_system",
#             "original_query": user_message,
#             "corrected_query": corrected_message,
#             "vad_metrics": vad_metrics
#         })
        
#     except Exception as e:
#         logger.error(f"Error processing with minipywo: {e}")
#         return jsonify({
#             "status": "error",
#             "message": str(e),
#             "source": "minipywo_error"
#         }), 500
@app.route('/api/minipywo', methods=['POST'])
def minipywo_proxy():
    # Tomamos el payload del cliente y lo reenviamos al endpoint FastAPI
    fastapi_url = "http://localhost:8000/api/minipywo"  # Ajusta la URL si es diferente
    try:
        response = requests.post(fastapi_url, json=request.get_json(), timeout=15)
        return (response.text, response.status_code, response.headers.items())
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 500

# ================================
# HEALTH AND MONITORING ENDPOINTS
# ================================

@app.route('/health')
def health():
    """Comprehensive health check endpoint"""
    
    # Check component status
    realtime_api_ok = bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY)
    minipywo_ok = MINIPYWO_AVAILABLE
    ice_server_ok = bool(ICE_SERVER_URL)
    
    # Test minipywo if available
    if MINIPYWO_AVAILABLE:
        try:
            test_config = {"configurable": {"thread_id": "health_check"}}
            test_result = wl_pywo.invoke({"question": "test"}, test_config)
            minipywo_ok = test_result is not None
        except:
            minipywo_ok = False
    
    # Determine overall status
    critical_ok = realtime_api_ok
    status = "healthy" if critical_ok else "unhealthy"
    if critical_ok and not (minipywo_ok and ice_server_ok):
        status = "degraded"
    
    return jsonify({
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'mode': 'AZURE_OPENAI_REALTIME_API_WITH_AVATAR',
        'components': {
            'realtime_api': {
                'status': 'healthy' if realtime_api_ok else 'unhealthy',
                'endpoint_configured': bool(AZURE_OPENAI_ENDPOINT),
                'api_key_configured': bool(AZURE_OPENAI_API_KEY),
                'deployment': AZURE_OPENAI_DEPLOYMENT,
                'api_version': AZURE_OPENAI_API_VERSION,
                'model': AZURE_OPENAI_MODEL
            },
            'minipywo_system': {
                'status': 'healthy' if minipywo_ok else 'unhealthy',
                'available': MINIPYWO_AVAILABLE,
                'corrections_active': MINIPYWO_AVAILABLE and len(original_list) > 0
            },
            'ice_server': {
                'status': 'healthy' if ice_server_ok else 'unhealthy',
                'configured': bool(ICE_SERVER_URL),
                'url': ICE_SERVER_URL if ice_server_ok else None
            },
            'avatar': {
                'enabled': ENABLE_AVATAR,
                'character': AVATAR_CHARACTER,
                'style': AVATAR_STYLE
            }
        },
        'features': {
            'realtime_conversation': realtime_api_ok,
            'avatar_support': realtime_api_ok and ENABLE_AVATAR,
            'ypf_knowledge_processing': minipywo_ok,
            'function_calling': minipywo_ok,
            'webrtc_connectivity': ice_server_ok
        },
        'endpoints': {
            'main_interface': '/',
            'realtime_config': '/api/voice-live-config',
            'minipywo_process': '/api/minipywo-process',
            'health_check': '/health',
            'metrics': '/metrics'
        },
        'sessions': {
            'active_count': len(client_sessions),
            'client_ids': list(client_sessions.keys())
        }
    }), 200 if status == "healthy" else 503

@app.route('/metrics')
def metrics():
    """Metrics endpoint for monitoring"""
    
    total_messages = sum(len(s['messages']) for s in client_sessions.values())
    
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'application': {
            'name': 'Azure OpenAI Realtime API Server',
            'version': '2.0.0',
            'environment': os.environ.get('NODE_ENV', 'production')
        },
        'sessions': {
            'total': len(client_sessions),
            'active': len([s for s in client_sessions.values() 
                          if len(s['messages']) > 0])
        },
        'messages': {
            'total': total_messages,
            'average_per_session': total_messages / max(len(client_sessions), 1)
        },
        'configuration': {
            'avatar_enabled': ENABLE_AVATAR,
            'minipywo_enabled': MINIPYWO_AVAILABLE,
            'ice_server_configured': bool(ICE_SERVER_URL),
            'language': LANGUAGE,
            'voice_model': VOICE_MODEL
        }
    })

# ================================
# SPEECH SERVICE CONFIG
# ================================


@app.route("/api/speech-config", methods=["GET"])
def get_speech_config():
    """Provide Speech Services configuration for avatar"""
    return jsonify({
        "speechKey": SPEECH_KEY,
        "speechRegion": SPEECH_REGION,
        "speechEndpoint": SPEECH_ENDPOINT
    })

# ================================
# WEBSOCKET EVENTS
# ================================

@socketio.on("connect")
def handle_connect():
    """Handle client connection"""
    client_id = request.args.get('client_id', generate_client_id())
    session = get_or_create_session(client_id)
    
    logger.info(f"Client connected: {client_id}")
    emit('status', {
        'message': 'Connected to Azure OpenAI Realtime API server',
        'client_id': client_id,
        'features': {
            'avatar': ENABLE_AVATAR,
            'minipywo': MINIPYWO_AVAILABLE
        }
    })

@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("Client disconnected")

@socketio.on("realtime_status")
def handle_realtime_status(data):
    """Receive status updates from Realtime API frontend"""
    logger.info(f"Realtime API status: {data}")
    emit('status', {
        'message': f"Realtime API: {data.get('status', 'unknown')}",
        'timestamp': datetime.now().isoformat()
    })

@socketio.on('process_message')
def handle_process_message(data):
    """Process message via Socket.IO"""
    if not MINIPYWO_AVAILABLE:
        emit('error', {'message': 'minipywo system not available'})
        return
    
    try:
        user_message = data.get('message', '')
        client_id = data.get('client_id', generate_client_id())
        
        logger.info(f"Socket.IO: Processing with minipywo: {user_message}")
        
        # Process with minipywo
        config = {"configurable": {"thread_id": client_id}}
        corrected_message = replace_token(user_message, original_list, replacement_list)
        
        result = wl_pywo.invoke({"question": corrected_message}, config)
        response_text = result.get("query_result", "Error processing YPF query")
        
        emit('process_response', {
            'message': response_text,
            'client_id': client_id,
            'source': 'minipywo_via_socketio',
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Socket.IO: Response sent: {response_text[:100]}...")
        
    except Exception as e:
        logger.error(f"Socket.IO Error: {e}")
        emit('error', {'message': f'Error: {str(e)}'})

# ================================
# COMPATIBILITY ROUTES
# ================================

@app.route("/chat")
def chat_view():
    """Legacy chat interface (fallback)"""
    return render_template("chat.html", client_id=generate_client_id())

@app.route("/api/chat", methods=["POST"])
def chat_api():
    """Legacy chat API (fallback)"""
    if not MINIPYWO_AVAILABLE:
        return Response("minipywo system not available", status=503)
    
    try:
        client_id = request.headers.get('ClientId', generate_client_id())
        user_query = request.data.decode('utf-8')
        
        # Process with minipywo
        config = {"configurable": {"thread_id": client_id}}
        corrected_message = replace_token(user_query, original_list, replacement_list)
        
        result = wl_pywo.invoke({"question": corrected_message}, config)
        response_text = result.get("query_result", "Error processing query")
        
        return Response(response_text, mimetype='text/plain', status=200)
        
    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return Response(f"Error: {str(e)}", status=500)

@app.route('/api/test-realtime', methods=["POST"])
def test_realtime():
    """Test endpoint for Realtime API configuration"""
    try:
        data = request.get_json()
        test_message = data.get('message', 'test message')
        
        return jsonify({
            "status": "success",
            "configuration": {
                "endpoint": AZURE_OPENAI_ENDPOINT,
                "deployment": AZURE_OPENAI_DEPLOYMENT,
                "api_version": AZURE_OPENAI_API_VERSION,
                "model": AZURE_OPENAI_MODEL,
                "avatar_enabled": ENABLE_AVATAR,
                "minipywo_available": MINIPYWO_AVAILABLE
            },
            "test_input": test_message,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# ================================
# ERROR HANDLERS
# ================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not found',
        'message': 'The requested resource was not found',
        'status_code': 404
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred',
        'status_code': 500
    }), 500

# ================================
# MAIN EXECUTION
# ================================

if __name__ == "__main__":
    logger.info("Starting Azure OpenAI Realtime API Server")
    logger.info("=" * 60)
    
    # Log configuration status
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        logger.error("CRITICAL: Azure OpenAI Realtime API not configured")
        logger.error("Configure AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY")
    else:
        logger.info(f"Azure OpenAI Realtime API configured: {AZURE_OPENAI_ENDPOINT}")
        logger.info(f"Deployment: {AZURE_OPENAI_DEPLOYMENT}")
        logger.info(f"API Version: {AZURE_OPENAI_API_VERSION}")
    
    if not MINIPYWO_AVAILABLE:
        logger.warning("minipywo system not available - function calling disabled")
    else:
        logger.info("minipywo system initialized successfully")
    
    if ICE_SERVER_URL:
        logger.info(f"ICE/TURN server configured: {ICE_SERVER_URL}")
    else:
        logger.warning("No ICE/TURN server configured - WebRTC may have connectivity issues")
    
    logger.info(f"Avatar support: {ENABLE_AVATAR}")
    logger.info(f"Voice model: {VOICE_MODEL}")
    logger.info(f"Language: {LANGUAGE}")
    
    logger.info("=" * 60)
    logger.info(f"Server starting on {FLASK_HOST}:{FLASK_PORT}")
    
    # Start server
    socketio.run(
        app,
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=False,
        use_reloader=False
    )