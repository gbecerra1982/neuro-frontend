# ================================
# AZURE OPENAI REALTIME API BACKEND
# Production Server with Avatar Support - Best Practices
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

# Avatar Configuration - Best Practices
ENABLE_AVATAR = os.environ.get('ENABLE_AVATAR', 'true').lower() == 'true'
AVATAR_CHARACTER = os.environ.get('AVATAR_CHARACTER', 'lisa')
AVATAR_STYLE = os.environ.get('AVATAR_STYLE', 'casual-sitting')
AVATAR_BACKGROUND_COLOR = os.environ.get('AVATAR_BACKGROUND_COLOR', '#FFFFFFFF')
AVATAR_BACKGROUND_IMAGE = os.environ.get('AVATAR_BACKGROUND_IMAGE', '')
AVATAR_RESOLUTION_WIDTH = int(os.environ.get('AVATAR_RESOLUTION_WIDTH', 1920))
AVATAR_RESOLUTION_HEIGHT = int(os.environ.get('AVATAR_RESOLUTION_HEIGHT', 1080))
AVATAR_VIDEO_BITRATE = int(os.environ.get('AVATAR_VIDEO_BITRATE', 2000000))  # 2 Mbps default
AVATAR_VIDEO_FRAMERATE = int(os.environ.get('AVATAR_VIDEO_FRAMERATE', 25))
AVATAR_VIDEO_CODEC = os.environ.get('AVATAR_VIDEO_CODEC', 'H264')
AVATAR_VIDEO_QUALITY = os.environ.get('AVATAR_VIDEO_QUALITY', 'high')

# Voice Configuration - Best Practices
VOICE_NAME = os.environ.get('VOICE_NAME', 'es-AR-TomasNeural')
VOICE_MODEL = os.environ.get('VOICE_MODEL', 'alloy')
VOICE_QUALITY = os.environ.get('VOICE_QUALITY', 'premium')
VOICE_PITCH = os.environ.get('VOICE_PITCH', '0Hz')
VOICE_RATE = os.environ.get('VOICE_RATE', '1.0')
VOICE_VOLUME = os.environ.get('VOICE_VOLUME', '100')
LANGUAGE = os.environ.get('LANGUAGE', 'es-AR')

# WebRTC Configuration - Best Practices
WEBRTC_MAX_BITRATE = int(os.environ.get('WEBRTC_MAX_BITRATE', 3000000))  # 3 Mbps
WEBRTC_MIN_BITRATE = int(os.environ.get('WEBRTC_MIN_BITRATE', 500000))   # 500 Kbps
WEBRTC_ENABLE_ECHO_CANCELLATION = os.environ.get('WEBRTC_ENABLE_ECHO_CANCELLATION', 'true').lower() == 'true'
WEBRTC_ENABLE_NOISE_SUPPRESSION = os.environ.get('WEBRTC_ENABLE_NOISE_SUPPRESSION', 'true').lower() == 'true'
WEBRTC_ENABLE_AUTO_GAIN_CONTROL = os.environ.get('WEBRTC_ENABLE_AUTO_GAIN_CONTROL', 'true').lower() == 'true'

# Performance Configuration
ENABLE_METRICS = os.environ.get('ENABLE_METRICS', 'true').lower() == 'true'
ENABLE_DETAILED_LOGGING = os.environ.get('ENABLE_DETAILED_LOGGING', 'false').lower() == 'true'
MAX_SESSION_DURATION = int(os.environ.get('MAX_SESSION_DURATION', 3600))  # 1 hour in seconds
SESSION_CLEANUP_INTERVAL = int(os.environ.get('SESSION_CLEANUP_INTERVAL', 300))  # 5 minutes

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

# Configure SocketIO with best practices
socketio = SocketIO(
    app, 
    cors_allowed_origins=cors_origins,
    ping_timeout=int(os.environ.get('SOCKETIO_PING_TIMEOUT', 20)),
    ping_interval=int(os.environ.get('SOCKETIO_PING_INTERVAL', 10)),
    max_http_buffer_size=int(os.environ.get('SOCKETIO_MAX_BUFFER_SIZE', 1000000)),
    async_mode='threading'
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
session_metrics = {}

def generate_client_id():
    """Generate unique client ID"""
    return str(uuid.uuid4())

def get_or_create_session(client_id):
    """Get or create client session with metrics"""
    if client_id not in client_sessions:
        client_sessions[client_id] = {
            'id': client_id,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
            'messages': [],
            'metadata': {},
            'avatar_state': 'idle',
            'connection_quality': 'unknown'
        }
        
        if ENABLE_METRICS:
            session_metrics[client_id] = {
                'message_count': 0,
                'total_duration': 0,
                'avatar_frames': 0,
                'audio_packets': 0,
                'errors': 0,
                'latency_samples': []
            }
    else:
        client_sessions[client_id]['last_activity'] = datetime.now().isoformat()
    
    return client_sessions[client_id]

# ================================
# MAIN ROUTES
# ================================

@app.route("/")
def index():
    """Main interface for Azure OpenAI Realtime API with Avatar"""
    client_id = generate_client_id()
    return render_template(
        "voice_live_interface.html",
        client_id=client_id
    )

@app.route("/api/voice-live-config", methods=["GET"])
def get_voice_live_config():
    """Provide optimized configuration for Realtime API with Avatar"""
    try:
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
            return jsonify({
                "error": "Azure OpenAI Realtime API not configured",
                "message": "Configure AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY"
            }), 400
        
        # Build optimized configuration with best practices
        config = {
            # Core Azure OpenAI Configuration
            "endpoint": AZURE_OPENAI_ENDPOINT,
            "apiKey": AZURE_OPENAI_API_KEY,
            "deployment": AZURE_OPENAI_DEPLOYMENT,
            "deploymentName": AZURE_OPENAI_DEPLOYMENT,
            "apiVersion": AZURE_OPENAI_API_VERSION,
            "model": AZURE_OPENAI_MODEL,
            "status": "ready",
            
            # Avatar Configuration with Best Practices
            "avatar": {
                "enabled": ENABLE_AVATAR,
                "character": AVATAR_CHARACTER,
                "style": AVATAR_STYLE,
                "background": {
                    "color": AVATAR_BACKGROUND_COLOR,
                    "image": AVATAR_BACKGROUND_IMAGE
                },
                "video": {
                    "bitrate": AVATAR_VIDEO_BITRATE,
                    "codec": AVATAR_VIDEO_CODEC,
                    "resolution": {
                        "width": AVATAR_RESOLUTION_WIDTH,
                        "height": AVATAR_RESOLUTION_HEIGHT
                    },
                    "frameRate": AVATAR_VIDEO_FRAMERATE,
                    "quality": AVATAR_VIDEO_QUALITY,
                    "keyFrameInterval": 2000,  # milliseconds
                    "hardwareAcceleration": True
                },
                "rendering": {
                    "antiAliasing": True,
                    "shadowQuality": "medium",
                    "textureQuality": "high"
                }
            },
            
            # Voice Configuration with Best Practices
            "voice": {
                "name": VOICE_NAME,
                "model": VOICE_MODEL,
                "quality": VOICE_QUALITY,
                "prosody": {
                    "pitch": VOICE_PITCH,
                    "rate": VOICE_RATE,
                    "volume": VOICE_VOLUME
                },
                "language": LANGUAGE,
                "outputFormat": "audio-24khz-96kbitrate-mono-mp3",
                "streamLatencyMode": "low"
            },
            
            # Speech SDK Specific Configuration
            "speechConfig": {
                "speechKey": SPEECH_KEY,
                "speechRegion": SPEECH_REGION,
                "speechEndpoint": SPEECH_ENDPOINT,
                "enableAvatarVideo": True,
                "avatarVideoBitrate": AVATAR_VIDEO_BITRATE,
                "avatarVideoCodec": AVATAR_VIDEO_CODEC,
                "avatarVideoFrameRate": AVATAR_VIDEO_FRAMERATE,
                "enableAutomaticReconnection": True,
                "connectionTimeout": 10000,  # milliseconds
                "recognitionMode": "conversation",
                "profanityOption": "masked",
                "enableDictation": True,
                "enableWordLevelTimestamps": True
            },
            
            # WebRTC Configuration with Best Practices
            "webrtc": {
                "maxBitrate": WEBRTC_MAX_BITRATE,
                "minBitrate": WEBRTC_MIN_BITRATE,
                "audioConstraints": {
                    "echoCancellation": WEBRTC_ENABLE_ECHO_CANCELLATION,
                    "noiseSuppression": WEBRTC_ENABLE_NOISE_SUPPRESSION,
                    "autoGainControl": WEBRTC_ENABLE_AUTO_GAIN_CONTROL,
                    "sampleRate": 48000,
                    "channelCount": 1
                },
                "videoConstraints": {
                    "width": {"ideal": AVATAR_RESOLUTION_WIDTH},
                    "height": {"ideal": AVATAR_RESOLUTION_HEIGHT},
                    "frameRate": {"ideal": AVATAR_VIDEO_FRAMERATE},
                    "facingMode": "user"
                },
                "iceTransportPolicy": "all",
                "bundlePolicy": "max-bundle",
                "rtcpMuxPolicy": "require",
                "sdpSemantics": "unified-plan"
            },
            
            # Performance and Optimization Settings
            "performance": {
                "enableMetrics": ENABLE_METRICS,
                "enableDetailedLogging": ENABLE_DETAILED_LOGGING,
                "maxSessionDuration": MAX_SESSION_DURATION,
                "bufferSize": 4096,
                "latencyHint": "interactive",
                "preloadAvatar": True,
                "cacheResponses": True,
                "enableCompression": True
            },
            
            # Features Configuration
            "features": {
                "avatar": ENABLE_AVATAR,
                "minipywo": MINIPYWO_AVAILABLE,
                "functionCalling": True,
                "streaming": True,
                "interruptions": True,
                "backgroundBlur": False,
                "noiseReduction": True,
                "autoReconnect": True
            }
        }
        
        # Add ICE/TURN servers if available
        if ICE_SERVER_URL:
            config["turnServers"] = [{
                "urls": ICE_SERVER_URL,
                "username": ICE_SERVER_USERNAME,
                "credential": ICE_SERVER_PASSWORD,
                "credentialType": "password"
            }]
            
            # Add STUN servers for better connectivity
            config["stunServers"] = [
                {"urls": "stun:stun.l.google.com:19302"},
                {"urls": "stun:stun1.l.google.com:19302"}
            ]
        
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

@app.route("/api/minipywo-process", methods=["POST"])
def api_minipywo_process():
    """Process query with minipywo system"""
    if not MINIPYWO_AVAILABLE:
        return jsonify({
            "status": "error",
            "message": "minipywo system not available"
        }), 503
    
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        client_id = data.get('client_id', generate_client_id())
        vad_metrics = data.get('vad_metrics', {})
        
        logger.info(f"Processing with minipywo: {user_message}")
        
        # Apply YPF corrections
        corrected_message = replace_token(user_message, original_list, replacement_list)
        
        # Configure minipywo
        config = {"configurable": {"thread_id": client_id}}
        
        # Process with minipywo
        result = wl_pywo.invoke({"question": corrected_message}, config)
        response_text = result.get("query_result", "Error processing YPF query")
        
        # Store in session
        session = get_or_create_session(client_id)
        session['messages'].append({
            'role': 'user',
            'content': user_message,
            'timestamp': datetime.now().isoformat()
        })
        session['messages'].append({
            'role': 'assistant',
            'content': response_text,
            'timestamp': datetime.now().isoformat()
        })
        
        # Update metrics if enabled
        if ENABLE_METRICS and client_id in session_metrics:
            session_metrics[client_id]['message_count'] += 2
        
        logger.info(f"minipywo response: {response_text[:100]}...")
        
        return jsonify({
            "status": "success",
            "response": response_text,
            "client_id": client_id,
            "source": "minipywo_ypf_system",
            "original_query": user_message,
            "corrected_query": corrected_message,
            "vad_metrics": vad_metrics,
            "processing_time": 0  # Add actual timing if needed
        })
        
    except Exception as e:
        logger.error(f"Error processing with minipywo: {e}")
        if ENABLE_METRICS and client_id in session_metrics:
            session_metrics[client_id]['errors'] += 1
        return jsonify({
            "status": "error",
            "message": str(e),
            "source": "minipywo_error"
        }), 500

# ================================
# SPEECH SERVICE CONFIGURATION
# ================================

@app.route("/api/speech-config", methods=["GET"])
def get_speech_config():
    """Provide comprehensive Speech Services configuration for avatar"""
    return jsonify({
        "speechKey": SPEECH_KEY,
        "speechRegion": SPEECH_REGION,
        "speechEndpoint": SPEECH_ENDPOINT,
        "voiceName": VOICE_NAME,
        "language": LANGUAGE,
        "avatarConfig": {
            "character": AVATAR_CHARACTER,
            "style": AVATAR_STYLE,
            "videoConfig": {
                "codec": AVATAR_VIDEO_CODEC,
                "bitrate": AVATAR_VIDEO_BITRATE,
                "frameRate": AVATAR_VIDEO_FRAMERATE,
                "resolution": f"{AVATAR_RESOLUTION_WIDTH}x{AVATAR_RESOLUTION_HEIGHT}"
            }
        }
    })

# ================================
# AVATAR CONTROL ENDPOINTS
# ================================

@app.route("/api/avatar/start", methods=["POST"])
def start_avatar():
    """Start avatar session with optimized settings"""
    try:
        data = request.get_json()
        client_id = data.get('client_id', generate_client_id())
        
        session = get_or_create_session(client_id)
        session['avatar_state'] = 'starting'
        
        return jsonify({
            "status": "success",
            "client_id": client_id,
            "avatar_config": {
                "character": AVATAR_CHARACTER,
                "style": AVATAR_STYLE,
                "video_bitrate": AVATAR_VIDEO_BITRATE,
                "video_codec": AVATAR_VIDEO_CODEC
            }
        })
    except Exception as e:
        logger.error(f"Error starting avatar: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/avatar/stop", methods=["POST"])
def stop_avatar():
    """Stop avatar session"""
    try:
        data = request.get_json()
        client_id = data.get('client_id')
        
        if client_id in client_sessions:
            client_sessions[client_id]['avatar_state'] = 'stopped'
        
        return jsonify({"status": "success", "client_id": client_id})
    except Exception as e:
        logger.error(f"Error stopping avatar: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ================================
# HEALTH AND MONITORING ENDPOINTS
# ================================

@app.route('/health')
def health():
    """Comprehensive health check endpoint with detailed status"""
    
    # Check component status
    realtime_api_ok = bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY)
    speech_service_ok = bool(SPEECH_KEY and SPEECH_REGION)
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
    critical_ok = realtime_api_ok and speech_service_ok
    status = "healthy" if critical_ok else "unhealthy"
    if critical_ok and not (minipywo_ok and ice_server_ok):
        status = "degraded"
    
    return jsonify({
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'mode': 'AZURE_SPEECH_LIVE_VOICE_WITH_AVATAR',
        'components': {
            'realtime_api': {
                'status': 'healthy' if realtime_api_ok else 'unhealthy',
                'endpoint_configured': bool(AZURE_OPENAI_ENDPOINT),
                'api_key_configured': bool(AZURE_OPENAI_API_KEY),
                'deployment': AZURE_OPENAI_DEPLOYMENT,
                'api_version': AZURE_OPENAI_API_VERSION,
                'model': AZURE_OPENAI_MODEL
            },
            'speech_service': {
                'status': 'healthy' if speech_service_ok else 'unhealthy',
                'key_configured': bool(SPEECH_KEY),
                'region': SPEECH_REGION,
                'endpoint': SPEECH_ENDPOINT
            },
            'avatar': {
                'enabled': ENABLE_AVATAR,
                'character': AVATAR_CHARACTER,
                'style': AVATAR_STYLE,
                'video_bitrate': AVATAR_VIDEO_BITRATE,
                'video_codec': AVATAR_VIDEO_CODEC,
                'resolution': f"{AVATAR_RESOLUTION_WIDTH}x{AVATAR_RESOLUTION_HEIGHT}"
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
            }
        },
        'features': {
            'realtime_conversation': realtime_api_ok,
            'avatar_support': realtime_api_ok and speech_service_ok and ENABLE_AVATAR,
            'ypf_knowledge_processing': minipywo_ok,
            'function_calling': minipywo_ok,
            'webrtc_connectivity': ice_server_ok,
            'metrics_enabled': ENABLE_METRICS
        },
        'performance': {
            'max_session_duration': MAX_SESSION_DURATION,
            'webrtc_max_bitrate': WEBRTC_MAX_BITRATE,
            'avatar_framerate': AVATAR_VIDEO_FRAMERATE
        },
        'endpoints': {
            'main_interface': '/',
            'realtime_config': '/api/voice-live-config',
            'speech_config': '/api/speech-config',
            'minipywo_process': '/api/minipywo-process',
            'avatar_start': '/api/avatar/start',
            'avatar_stop': '/api/avatar/stop',
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
    """Enhanced metrics endpoint for monitoring"""
    
    total_messages = sum(len(s['messages']) for s in client_sessions.values())
    total_errors = sum(m.get('errors', 0) for m in session_metrics.values()) if ENABLE_METRICS else 0
    
    metrics_data = {
        'timestamp': datetime.now().isoformat(),
        'application': {
            'name': 'Azure Speech Live Voice with Avatar Server',
            'version': '2.1.0',
            'environment': os.environ.get('NODE_ENV', 'production')
        },
        'sessions': {
            'total': len(client_sessions),
            'active': len([s for s in client_sessions.values() 
                          if len(s['messages']) > 0]),
            'with_avatar': len([s for s in client_sessions.values() 
                               if s.get('avatar_state') == 'active'])
        },
        'messages': {
            'total': total_messages,
            'average_per_session': total_messages / max(len(client_sessions), 1)
        },
        'errors': {
            'total': total_errors,
            'rate': total_errors / max(total_messages, 1) if total_messages > 0 else 0
        },
        'configuration': {
            'avatar_enabled': ENABLE_AVATAR,
            'minipywo_enabled': MINIPYWO_AVAILABLE,
            'ice_server_configured': bool(ICE_SERVER_URL),
            'language': LANGUAGE,
            'voice_model': VOICE_MODEL,
            'voice_quality': VOICE_QUALITY,
            'avatar_resolution': f"{AVATAR_RESOLUTION_WIDTH}x{AVATAR_RESOLUTION_HEIGHT}",
            'avatar_bitrate': AVATAR_VIDEO_BITRATE,
            'webrtc_max_bitrate': WEBRTC_MAX_BITRATE
        }
    }
    
    # Add detailed session metrics if enabled
    if ENABLE_METRICS and session_metrics:
        metrics_data['detailed_metrics'] = {
            'sessions': session_metrics,
            'aggregate': {
                'total_message_count': sum(m.get('message_count', 0) for m in session_metrics.values()),
                'total_avatar_frames': sum(m.get('avatar_frames', 0) for m in session_metrics.values()),
                'total_audio_packets': sum(m.get('audio_packets', 0) for m in session_metrics.values())
            }
        }
    
    return jsonify(metrics_data)

# ================================
# WEBSOCKET EVENTS WITH BEST PRACTICES
# ================================

@socketio.on("connect")
def handle_connect():
    """Handle client connection with enhanced logging"""
    client_id = request.args.get('client_id', generate_client_id())
    session = get_or_create_session(client_id)
    
    logger.info(f"Client connected: {client_id}")
    
    emit('status', {
        'message': 'Connected to Azure Speech Live Voice with Avatar server',
        'client_id': client_id,
        'features': {
            'avatar': ENABLE_AVATAR,
            'minipywo': MINIPYWO_AVAILABLE,
            'speech_service': bool(SPEECH_KEY),
            'webrtc': bool(ICE_SERVER_URL)
        },
        'configuration': {
            'voice_model': VOICE_MODEL,
            'avatar_character': AVATAR_CHARACTER,
            'language': LANGUAGE
        }
    })

@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection with cleanup"""
    logger.info("Client disconnected")
    # Add cleanup logic if needed

@socketio.on("realtime_status")
def handle_realtime_status(data):
    """Receive enhanced status updates from Realtime API frontend"""
    logger.info(f"Realtime API status: {data}")
    
    client_id = data.get('client_id')
    if client_id and client_id in client_sessions:
        client_sessions[client_id]['connection_quality'] = data.get('quality', 'unknown')
        
        if ENABLE_METRICS and client_id in session_metrics:
            if 'latency' in data:
                session_metrics[client_id]['latency_samples'].append(data['latency'])
    
    emit('status', {
        'message': f"Realtime API: {data.get('status', 'unknown')}",
        'timestamp': datetime.now().isoformat(),
        'details': data
    })

@socketio.on('process_message')
def handle_process_message(data):
    """Process message via Socket.IO with enhanced error handling"""
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
        
        # Update metrics
        if ENABLE_METRICS and client_id in session_metrics:
            session_metrics[client_id]['message_count'] += 1
        
        emit('process_response', {
            'message': response_text,
            'client_id': client_id,
            'source': 'minipywo_via_socketio',
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Socket.IO: Response sent: {response_text[:100]}...")
        
    except Exception as e:
        logger.error(f"Socket.IO Error: {e}")
        if ENABLE_METRICS and client_id in session_metrics:
            session_metrics[client_id]['errors'] += 1
        emit('error', {'message': f'Error: {str(e)}'})

@socketio.on('avatar_frame')
def handle_avatar_frame(data):
    """Handle avatar frame updates for metrics"""
    if ENABLE_METRICS:
        client_id = data.get('client_id')
        if client_id and client_id in session_metrics:
            session_metrics[client_id]['avatar_frames'] += 1

@socketio.on('audio_packet')
def handle_audio_packet(data):
    """Handle audio packet for metrics"""
    if ENABLE_METRICS:
        client_id = data.get('client_id')
        if client_id and client_id in session_metrics:
            session_metrics[client_id]['audio_packets'] += 1

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
                "avatar_config": {
                    "character": AVATAR_CHARACTER,
                    "bitrate": AVATAR_VIDEO_BITRATE,
                    "codec": AVATAR_VIDEO_CODEC
                },
                "speech_service": {
                    "configured": bool(SPEECH_KEY),
                    "region": SPEECH_REGION
                },
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
# SESSION CLEANUP
# ================================

def cleanup_old_sessions():
    """Clean up old sessions periodically"""
    try:
        current_time = datetime.now()
        sessions_to_remove = []
        
        for client_id, session in client_sessions.items():
            last_activity = datetime.fromisoformat(session['last_activity'])
            if (current_time - last_activity).seconds > MAX_SESSION_DURATION:
                sessions_to_remove.append(client_id)
        
        for client_id in sessions_to_remove:
            del client_sessions[client_id]
            if client_id in session_metrics:
                del session_metrics[client_id]
            logger.info(f"Cleaned up session: {client_id}")
        
        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")
    
    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")

# Schedule periodic cleanup (you may want to use a proper scheduler in production)
import threading
def schedule_cleanup():
    cleanup_old_sessions()
    timer = threading.Timer(SESSION_CLEANUP_INTERVAL, schedule_cleanup)
    timer.daemon = True
    timer.start()

# ================================
# MAIN EXECUTION
# ================================

if __name__ == "__main__":
    logger.info("Starting Azure Speech Live Voice with Avatar Server")
    logger.info("=" * 60)
    
    # Log configuration status
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        logger.error("CRITICAL: Azure OpenAI Realtime API not configured")
        logger.error("Configure AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY")
    else:
        logger.info(f"Azure OpenAI Realtime API configured: {AZURE_OPENAI_ENDPOINT}")
        logger.info(f"Deployment: {AZURE_OPENAI_DEPLOYMENT}")
        logger.info(f"API Version: {AZURE_OPENAI_API_VERSION}")
    
    if not SPEECH_KEY or not SPEECH_REGION:
        logger.warning("Speech Service not configured - Avatar features limited")
    else:
        logger.info(f"Speech Service configured: Region {SPEECH_REGION}")
    
    if not MINIPYWO_AVAILABLE:
        logger.warning("minipywo system not available - function calling disabled")
    else:
        logger.info("minipywo system initialized successfully")
    
    if ICE_SERVER_URL:
        logger.info(f"ICE/TURN server configured: {ICE_SERVER_URL}")
    else:
        logger.warning("No ICE/TURN server configured - WebRTC may have connectivity issues")
    
    logger.info(f"Avatar support: {ENABLE_AVATAR}")
    if ENABLE_AVATAR:
        logger.info(f"  Character: {AVATAR_CHARACTER}")
        logger.info(f"  Style: {AVATAR_STYLE}")
        logger.info(f"  Video: {AVATAR_RESOLUTION_WIDTH}x{AVATAR_RESOLUTION_HEIGHT} @ {AVATAR_VIDEO_FRAMERATE}fps")
        logger.info(f"  Bitrate: {AVATAR_VIDEO_BITRATE / 1000000:.1f} Mbps")
        logger.info(f"  Codec: {AVATAR_VIDEO_CODEC}")
    
    logger.info(f"Voice configuration:")
    logger.info(f"  Model: {VOICE_MODEL}")
    logger.info(f"  Name: {VOICE_NAME}")
    logger.info(f"  Quality: {VOICE_QUALITY}")
    logger.info(f"  Language: {LANGUAGE}")
    
    logger.info(f"WebRTC configuration:")
    logger.info(f"  Max bitrate: {WEBRTC_MAX_BITRATE / 1000000:.1f} Mbps")
    logger.info(f"  Echo cancellation: {WEBRTC_ENABLE_ECHO_CANCELLATION}")
    logger.info(f"  Noise suppression: {WEBRTC_ENABLE_NOISE_SUPPRESSION}")
    
    logger.info(f"Performance settings:")
    logger.info(f"  Metrics enabled: {ENABLE_METRICS}")
    logger.info(f"  Max session duration: {MAX_SESSION_DURATION}s")
    
    logger.info("=" * 60)
    logger.info(f"Server starting on {FLASK_HOST}:{FLASK_PORT}")
    
    # Start session cleanup scheduler
    if SESSION_CLEANUP_INTERVAL > 0:
        schedule_cleanup()
        logger.info(f"Session cleanup scheduled every {SESSION_CLEANUP_INTERVAL}s")
    
    # Start server
    socketio.run(
        app,
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=False,
        use_reloader=False
    )