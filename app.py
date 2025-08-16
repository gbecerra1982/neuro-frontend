# ================================
# AZURE OPENAI REALTIME API BACKEND
# Production Server with Avatar Support - Hardened with Socket.IO Proxy
# ================================

from flask import Flask, render_template, Response, request, jsonify, make_response, g
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import sys
import json
import uuid
import logging
import threading
import secrets
from datetime import datetime
from dotenv import load_dotenv

# 3rd party for Speech STS and WebSocket proxy
import requests
try:
    # Intentar importar websocket-client
    import websocket
    if not hasattr(websocket, 'WebSocketApp'):
        raise ImportError("websocket module doesn't have WebSocketApp")
except ImportError:
    # Si falla, intentar con el nombre alternativo
    try:
        from websocket import WebSocketApp
        import websocket
    except ImportError:
        logger.error("websocket-client not installed. Install with: pip install websocket-client")
        raise

# Import YPF minipywo system (opcional)
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
    level=os.environ.get('LOG_LEVEL', 'WARNING'),  # Cambiar a WARNING para reducir logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reducir el nivel de logging de werkzeug y engineio
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('engineio.server').setLevel(logging.WARNING)
logging.getLogger('socketio.server').setLevel(logging.WARNING)

# Si quieres ver más detalles, solo para este módulo
if os.environ.get('DEBUG_MODE', 'false').lower() == 'true':
    logger.setLevel(logging.DEBUG)
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    logging.getLogger('engineio.server').setLevel(logging.INFO)
    logging.getLogger('socketio.server').setLevel(logging.INFO)

# ================================
# ENVIRONMENT VARIABLES
# ================================

# Azure OpenAI Realtime API Configuration
AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT')
AZURE_OPENAI_API_KEY = os.environ.get('AZURE_OPENAI_API_KEY')  # <-- no se expone al front
AZURE_OPENAI_DEPLOYMENT = os.environ.get('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o-realtime-preview')
AZURE_OPENAI_API_VERSION = os.environ.get('AZURE_OPENAI_API_VERSION', '2025-04-01-preview')
AZURE_OPENAI_MODEL = os.environ.get('AZURE_OPENAI_MODEL', 'gpt-4o-realtime-preview')

# Speech Service Config (claves nunca al front)
SPEECH_KEY = os.environ.get('SPEECH_KEY')
SPEECH_ENDPOINT = os.environ.get('SPEECH_ENDPOINT')
SPEECH_REGION = os.environ.get('SPEECH_REGION')

# ICE/TURN Server Configuration (opcional)
ICE_SERVER_URL = os.environ.get('ICE_SERVER_URL')
ICE_SERVER_USERNAME = os.environ.get('ICE_SERVER_USERNAME')
ICE_SERVER_PASSWORD = os.environ.get('ICE_SERVER_PASSWORD')

# Avatar Configuration
ENABLE_AVATAR = os.environ.get('ENABLE_AVATAR', 'true').lower() == 'true'
AVATAR_CHARACTER = os.environ.get('AVATAR_CHARACTER', 'lisa')
AVATAR_STYLE = os.environ.get('AVATAR_STYLE', 'casual-sitting')
AVATAR_BACKGROUND_COLOR = os.environ.get('AVATAR_BACKGROUND_COLOR', '#FFFFFFFF')
AVATAR_BACKGROUND_IMAGE = os.environ.get('AVATAR_BACKGROUND_IMAGE', '')
AVATAR_RESOLUTION_WIDTH = int(os.environ.get('AVATAR_RESOLUTION_WIDTH', 1920))
AVATAR_RESOLUTION_HEIGHT = int(os.environ.get('AVATAR_RESOLUTION_HEIGHT', 1080))
AVATAR_VIDEO_BITRATE = int(os.environ.get('AVATAR_VIDEO_BITRATE', 2000000))
AVATAR_VIDEO_FRAMERATE = int(os.environ.get('AVATAR_VIDEO_FRAMERATE', 25))
AVATAR_VIDEO_CODEC = os.environ.get('AVATAR_VIDEO_CODEC', 'H264')
AVATAR_VIDEO_QUALITY = os.environ.get('AVATAR_VIDEO_QUALITY', 'high')

# Voice Configuration
VOICE_NAME = os.environ.get('VOICE_NAME', 'es-AR-TomasNeural')
VOICE_MODEL = os.environ.get('VOICE_MODEL', 'alloy')
VOICE_QUALITY = os.environ.get('VOICE_QUALITY', 'premium')
VOICE_PITCH = os.environ.get('VOICE_PITCH', '0Hz')
VOICE_RATE = os.environ.get('VOICE_RATE', '1.0')
VOICE_VOLUME = os.environ.get('VOICE_VOLUME', '100')
LANGUAGE = os.environ.get('LANGUAGE', 'es-AR')

# WebRTC Configuration
WEBRTC_MAX_BITRATE = int(os.environ.get('WEBRTC_MAX_BITRATE', 3000000))
WEBRTC_MIN_BITRATE = int(os.environ.get('WEBRTC_MIN_BITRATE', 500000))
WEBRTC_ENABLE_ECHO_CANCELLATION = os.environ.get('WEBRTC_ENABLE_ECHO_CANCELLATION', 'true').lower() == 'true'
WEBRTC_ENABLE_NOISE_SUPPRESSION = os.environ.get('WEBRTC_ENABLE_NOISE_SUPPRESSION', 'true').lower() == 'true'
WEBRTC_ENABLE_AUTO_GAIN_CONTROL = os.environ.get('WEBRTC_ENABLE_AUTO_GAIN_CONTROL', 'true').lower() == 'true'

# Performance Configuration
ENABLE_METRICS = os.environ.get('ENABLE_METRICS', 'true').lower() == 'true'
ENABLE_DETAILED_LOGGING = os.environ.get('ENABLE_DETAILED_LOGGING', 'false').lower() == 'true'
MAX_SESSION_DURATION = int(os.environ.get('MAX_SESSION_DURATION', 3600))
SESSION_CLEANUP_INTERVAL = int(os.environ.get('SESSION_CLEANUP_INTERVAL', 300))

# Server Configuration
FLASK_PORT = int(os.environ.get('FLASK_PORT', 5000))
FLASK_HOST = os.environ.get('FLASK_HOST', '0.0.0.0')

# Version & Templates centralizados
APP_VERSION = os.environ.get('APP_VERSION', '2.1.0')
TEMPLATES = {
    'main': os.environ.get('TEMPLATE_MAIN', 'voice_live_interface.html'),
    'chat': os.environ.get('TEMPLATE_CHAT', 'chat.html')
}

# Correcciones de texto (archivo externo)
TEXT_CORRECTIONS_FILE = os.environ.get('TEXT_CORRECTIONS_FILE', 'config/text_corrections.json')

def load_text_corrections():
    try:
        with open(TEXT_CORRECTIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('original', []), data.get('replacement', [])
    except Exception as e:
        logger.warning(f"Text corrections file not found or invalid ({TEXT_CORRECTIONS_FILE}): {e}")
        return [], []

original_list, replacement_list = load_text_corrections()

# ================================
# FLASK APPLICATION SETUP
# ================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET', str(uuid.uuid4()))

# CORS
cors_origins = os.environ.get('CORS_ORIGINS', '*').split(',')
CORS(app, origins=cors_origins)

# SocketIO with proper configuration for Socket.IO CDN
socketio = SocketIO(
    app,
    cors_allowed_origins="*",  # Allow all origins for Socket.IO
    ping_timeout=int(os.environ.get('SOCKETIO_PING_TIMEOUT', 20)),
    ping_interval=int(os.environ.get('SOCKETIO_PING_INTERVAL', 10)),
    max_http_buffer_size=int(os.environ.get('SOCKETIO_MAX_BUFFER_SIZE', 1000000)),
    async_mode='threading',
    logger=False,  # Disable Socket.IO logging to reduce noise
    engineio_logger=False  # Set to True for debugging
)

# ================================
# REALTIME API WEBSOCKET PROXY
# ================================

# Diccionario para mantener las conexiones WebSocket del Realtime API
realtime_connections = {}
realtime_threads = {}

class RealtimeWebSocketProxy:
    """Clase para manejar el proxy del WebSocket de Azure OpenAI Realtime API"""
    
    def __init__(self, client_id, sid):
        self.client_id = client_id
        self.sid = sid
        self.ws = None
        self.is_connected = False
        self.thread = None
        
    def connect(self):
        """Establece conexión con Azure OpenAI Realtime API"""
        try:
            # Construir la URL del WebSocket
            endpoint = AZURE_OPENAI_ENDPOINT.replace('https://', 'wss://').rstrip('/')
            deployment = AZURE_OPENAI_DEPLOYMENT
            api_version = AZURE_OPENAI_API_VERSION
            api_key = AZURE_OPENAI_API_KEY
            
            ws_url = f"{endpoint}/openai/realtime?api-version={api_version}&deployment={deployment}&api-key={api_key}"
            
            logger.info(f"Connecting to Realtime API for client {self.client_id}")
            logger.debug(f"WebSocket URL: {endpoint}/openai/realtime")
            
            # Crear WebSocket
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            # Ejecutar en thread separado
            self.thread = threading.Thread(target=self.ws.run_forever)
            self.thread.daemon = True
            self.thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Realtime API: {e}")
            socketio.emit('realtime_error', {
                'error': str(e),
                'client_id': self.client_id
            }, room=self.sid)
            return False
    
    def on_open(self, ws):
        """Callback cuando se abre la conexión"""
        logger.info(f"Realtime WebSocket opened for client {self.client_id}")
        self.is_connected = True
        socketio.emit('realtime_connected', {
            'status': 'connected',
            'client_id': self.client_id
        }, room=self.sid)
    
    def on_message(self, ws, message):
        """Callback cuando se recibe un mensaje"""
        try:
            # Reenviar el mensaje al cliente via Socket.IO
            socketio.emit('realtime_message', {
                'data': message,
                'client_id': self.client_id
            }, room=self.sid)
            
            if ENABLE_DETAILED_LOGGING:
                msg_data = json.loads(message)
                msg_type = msg_data.get('type', 'unknown')
                # Solo loguear eventos importantes, no audio
                if msg_type not in ['response.audio.delta', 'response.audio_transcript.delta']:
                    logger.debug(f"Realtime message type: {msg_type}")
                
        except Exception as e:
            logger.error(f"Error processing Realtime message: {e}")
    
    def on_error(self, ws, error):
        """Callback cuando ocurre un error"""
        logger.error(f"Realtime WebSocket error for client {self.client_id}: {error}")
        socketio.emit('realtime_error', {
            'error': str(error),
            'client_id': self.client_id
        }, room=self.sid)
    
    def on_close(self, ws, close_status_code=None, close_msg=None):
        """Callback cuando se cierra la conexión"""
        logger.info(f"Realtime WebSocket closed for client {self.client_id} (code: {close_status_code}, msg: {close_msg})")
        self.is_connected = False
        try:
            socketio.emit('realtime_closed', {
                'status': 'disconnected',
                'client_id': self.client_id,
                'code': close_status_code,
                'message': close_msg
            }, room=self.sid)
        except Exception as e:
            logger.error(f"Error emitting realtime_closed: {e}")
    
    def send(self, message):
        """Envía un mensaje al WebSocket de Azure"""
        if self.ws and self.is_connected:
            try:
                if isinstance(message, dict):
                    message = json.dumps(message)
                self.ws.send(message)
                return True
            except Exception as e:
                logger.error(f"Error sending message to Realtime API: {e}")
                return False
        else:
            logger.warning(f"Cannot send message - WebSocket not connected for client {self.client_id}")
            return False
    
    def close(self):
        """Cierra la conexión WebSocket"""
        if self.ws:
            try:
                self.ws.close()
                self.is_connected = False
                logger.info(f"Closed Realtime WebSocket for client {self.client_id}")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

# ================================
# SOCKET.IO REALTIME PROXY EVENTS
# ================================

@socketio.on('realtime_connect')
def handle_realtime_connect(data):
    """Establece conexión proxy con Azure OpenAI Realtime API"""
    client_id = data.get('client_id')
    
    if not client_id:
        emit('realtime_error', {'error': 'No client_id provided'})
        return
    
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        emit('realtime_error', {'error': 'Azure OpenAI Realtime API not configured'})
        return
    
    try:
        # Cerrar conexión anterior si existe
        if client_id in realtime_connections:
            old_proxy = realtime_connections[client_id]
            old_proxy.close()
            del realtime_connections[client_id]
        
        # Crear nuevo proxy
        proxy = RealtimeWebSocketProxy(client_id, request.sid)
        
        # Conectar al Realtime API
        if proxy.connect():
            realtime_connections[client_id] = proxy
            logger.info(f"Realtime proxy established for client {client_id}")
        else:
            emit('realtime_error', {'error': 'Failed to connect to Realtime API'})
            
    except Exception as e:
        logger.error(f"Error establishing Realtime proxy: {e}")
        emit('realtime_error', {'error': str(e)})

@socketio.on('realtime_send')
def handle_realtime_send(data):
    """Envía mensaje al WebSocket de Azure OpenAI Realtime API"""
    client_id = data.get('client_id')
    message = data.get('message')
    
    if not client_id or not message:
        emit('realtime_error', {'error': 'Missing client_id or message'})
        return
    
    if client_id not in realtime_connections:
        emit('realtime_error', {'error': 'No active connection for this client'})
        return
    
    try:
        proxy = realtime_connections[client_id]
        if proxy.send(message):
            if ENABLE_DETAILED_LOGGING:
                msg_type = message.get('type', 'unknown') if isinstance(message, dict) else 'raw'
                # Solo loguear mensajes que no sean audio
                if msg_type != 'input_audio_buffer.append':
                    logger.debug(f"Sent message to Realtime API: {msg_type}")
        else:
            emit('realtime_error', {'error': 'Failed to send message to Realtime API'})
            
    except Exception as e:
        logger.error(f"Error sending to Realtime API: {e}")
        emit('realtime_error', {'error': str(e)})

@socketio.on('realtime_disconnect')
def handle_realtime_disconnect(data):
    """Cierra la conexión proxy con Azure OpenAI Realtime API"""
    client_id = data.get('client_id')
    
    if not client_id:
        return
    
    try:
        if client_id in realtime_connections:
            proxy = realtime_connections[client_id]
            proxy.close()
            del realtime_connections[client_id]
            logger.info(f"Realtime proxy disconnected for client {client_id}")
            emit('realtime_disconnected', {'status': 'disconnected'})
        else:
            logger.warning(f"No connection to disconnect for client {client_id}")
            emit('realtime_error', {'error': 'No connection to disconnect'})
            
    except KeyError as e:
        logger.warning(f"Client {client_id} not found in connections")
    except Exception as e:
        logger.error(f"Error disconnecting Realtime proxy: {e}")
        emit('realtime_error', {'error': str(e)})

# ================================
# STARTUP VALIDATION & SECURITY
# ================================
def validate_required_environment_variables():
    required = {
        'AZURE_OPENAI_ENDPOINT': 'Azure OpenAI endpoint URL',
        'AZURE_OPENAI_API_KEY': 'Azure OpenAI API key',
        'SPEECH_KEY': 'Azure Speech Service key',
        'SPEECH_REGION': 'Azure Speech Service region'
    }
    missing = [k for k, _ in required.items() if not os.environ.get(k)]
    if missing:
        logger.error("Missing required environment variables: %s", missing)
        sys.exit(1)
    logger.warning("All required environment variables are set")

# === Nonce por request e inyección a plantillas ===
@app.before_request
def set_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)

@app.context_processor
def inject_csp_nonce():
    # Permite usar {{ csp_nonce }} en cualquier plantilla
    return {"csp_nonce": getattr(g, "csp_nonce", "")}

@app.after_request
def add_security_headers(response):
    # CSP por header (no usar <meta http-equiv="Content-Security-Policy"> en el HTML)
    nonce = getattr(g, "csp_nonce", "")
    
    # CSP más permisivo para desarrollo
    csp = (
        "default-src 'self'; "
        # Scripts con nonce y CDNs necesarios, incluyendo unsafe-eval para SDK
        f"script-src 'self' 'nonce-{nonce}' 'unsafe-eval' "
        "https://cdn.jsdelivr.net "
        "https://aka.ms "
        "https://cdn.socket.io "
        "*.cognitive.microsoft.com "
        "*.cognitiveservices.azure.com; "
        # Conexiones permitidas
        "connect-src 'self' http: https: ws: wss: blob: data:; "
        # Imágenes y media
        "img-src 'self' data: blob: https:; "
        "media-src 'self' blob: mediastream: https:; "
        # Estilos con unsafe-inline temporalmente
        f"style-src 'self' 'nonce-{nonce}' 'unsafe-inline'; "
        # Fonts
        "font-src 'self' data: https:; "
        # Workers y frames
        "worker-src 'self' blob:; "
        "frame-src 'none'; "
        # Object
        "object-src 'none'; "
        "base-uri 'self'; "
    )
    
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = "microphone=(self), camera=(self)"
    
    # Agregar headers CORS adicionales si es necesario
    origin = request.headers.get('Origin')
    if origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    
    return response

# ================================
# MINIPYWO INIT (opcional)
# ================================
if MINIPYWO_AVAILABLE:
    try:
        wl_pywo = minipywo_app()
        logger.info("minipywo system initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize minipywo: {e}")
        MINIPYWO_AVAILABLE = False

# ================================
# CLIENT SESSION MGMT
# ================================
client_sessions = {}
session_metrics = {}

def generate_client_id():
    return str(uuid.uuid4())

def get_or_create_session(client_id):
    if client_id not in client_sessions:
        client_sessions[client_id] = {
            'id': client_id,
            'created_at': datetime.now().isoformat(),
            'last_activity': datetime.now().isoformat(),
            'messages': [],
            'metadata': {},
            'avatar_state': 'idle',
            'connection_quality': 'unknown',
            'realtime_connected': False
        }
        if ENABLE_METRICS:
            session_metrics[client_id] = {
                'message_count': 0,
                'total_duration': 0,
                'avatar_frames': 0,
                'audio_packets': 0,
                'errors': 0,
                'latency_samples': [],
                'realtime_messages': 0
            }
    else:
        client_sessions[client_id]['last_activity'] = datetime.now().isoformat()
    return client_sessions[client_id]

# ================================
# ROUTES
# ================================
@app.route("/")
def index():
    client_id = generate_client_id()
    return render_template(TEMPLATES['main'], client_id=client_id)

@app.route("/chat")
def chat_view():
    return render_template(TEMPLATES['chat'], client_id=generate_client_id())

@app.route("/api/voice-live-config", methods=["GET"])
def get_voice_live_config():
    """
    Config Realtime/Avatar para el front.
    NO expone apiKey ni speechKey ni endpoint. El front usará Socket.IO proxy.
    """
    try:
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
            return jsonify({
                "error": "Azure OpenAI Realtime API not configured",
                "message": "Configure AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY"
            }), 400

        config = {
            "status": "ready",
            "deployment": AZURE_OPENAI_DEPLOYMENT,
            "deploymentName": AZURE_OPENAI_DEPLOYMENT,
            "apiVersion": AZURE_OPENAI_API_VERSION,
            "model": AZURE_OPENAI_MODEL,
            "useProxy": True,  # Indicar que usamos proxy Socket.IO

            # Avatar
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
                    "keyFrameInterval": 2000,
                    "hardwareAcceleration": True
                }
            },

            # Voice
            "voice": {
                "name": VOICE_NAME,
                "model": VOICE_MODEL,
                "quality": VOICE_QUALITY,
                "prosody": { "pitch": VOICE_PITCH, "rate": VOICE_RATE, "volume": VOICE_VOLUME },
                "language": LANGUAGE,
                "outputFormat": "audio-24khz-96kbitrate-mono-mp3",
                "streamLatencyMode": "low"
            },

            # WebRTC
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

            # Perf/Features
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
            "features": {
                "avatar": ENABLE_AVATAR,
                "minipywo": MINIPYWO_AVAILABLE,
                "functionCalling": True,
                "streaming": True,
                "interruptions": True,
                "backgroundBlur": False,
                "noiseReduction": True,
                "autoReconnect": True,
                "realtimeProxy": True  # Indicar que usamos proxy
            }
        }

        if ICE_SERVER_URL:
            config["turnServers"] = [{
                "urls": ICE_SERVER_URL,
                "username": ICE_SERVER_USERNAME,
                "credential": ICE_SERVER_PASSWORD,
                "credentialType": "password"
            }]
            config["stunServers"] = [
                {"urls": "stun:stun.l.google.com:19302"},
                {"urls": "stun:stun1.l.google.com:19302"}
            ]

        if MINIPYWO_AVAILABLE:
            config["tools"] = [{
                "type": "function",
                "name": "query_minipywo",
                "description": "Query minipywo system for YPF equipment, wells, workover, and technical data",
                "parameters": {
                    "type": "object",
                    "properties": { "query": { "type": "string", "description": "User query to be processed by minipywo" } },
                    "required": ["query"]
                }
            }]

        return jsonify(config)

    except Exception as e:
        logger.error(f"Error getting Realtime API config: {e}")
        return jsonify({"error": str(e)}), 500

# ==== Speech Service (sin exponer claves) ====

@app.route("/api/speech-config", methods=["GET"])
def get_speech_config():
    """Config pública para el front SIN KEYS"""
    return jsonify({
        # No mandar speechKey
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

@app.route("/api/speech-token", methods=["GET"])
def get_speech_token():
    """
    Emite token temporal STS para Azure Speech (10 min).
    Debe usarse desde el front para Relay/Avatar/WebRTC.
    """
    try:
        if not SPEECH_KEY or not SPEECH_REGION:
            return jsonify({"error": "Speech Service not configured"}), 400

        token_endpoint = f"https://{SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issuetoken"
        resp = requests.post(
            token_endpoint,
            headers={
                'Ocp-Apim-Subscription-Key': SPEECH_KEY,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            timeout=10
        )
        if resp.status_code == 200 and resp.text:
            return jsonify({
                "token": resp.text,
                "region": SPEECH_REGION,
                "expiresIn": 600
            })
        logger.error(f"Failed to get speech token: {resp.status_code} {resp.text}")
        return jsonify({"error": "Failed to generate token"}), 502
    except Exception as e:
        logger.error(f"Error generating speech token: {e}")
        return jsonify({"error": str(e)}), 500

# ==== minipywo API (sin cambios funcionales) ====

@app.route("/api/minipywo-process", methods=["POST"])
def api_minipywo_process():
    if not MINIPYWO_AVAILABLE:
        return jsonify({ "status": "error", "message": "minipywo system not available" }), 503
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        client_id = data.get('client_id', generate_client_id())
        vad_metrics = data.get('vad_metrics', {})

        logger.info(f"Processing with minipywo: {user_message}")

        corrected_message = replace_token(user_message, original_list, replacement_list)
        config = {"configurable": {"thread_id": client_id}}
        result = wl_pywo.invoke({"question": corrected_message}, config)
        response_text = result.get("query_result", "Error processing YPF query")

        session = get_or_create_session(client_id)
        session['messages'].append({'role': 'user','content': user_message,'timestamp': datetime.now().isoformat()})
        session['messages'].append({'role': 'assistant','content': response_text,'timestamp': datetime.now().isoformat()})

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
            "processing_time": 0
        })
    except Exception as e:
        logger.error(f"Error processing with minipywo: {e}")
        if ENABLE_METRICS and client_id in session_metrics:
            session_metrics[client_id]['errors'] += 1
        return jsonify({ "status": "error", "message": str(e), "source": "minipywo_error" }), 500

# ==== Avatar control ====

@app.route("/api/avatar/start", methods=["POST"])
def start_avatar():
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
    try:
        data = request.get_json()
        client_id = data.get('client_id')
        if client_id in client_sessions:
            client_sessions[client_id]['avatar_state'] = 'stopped'
        return jsonify({"status": "success", "client_id": client_id})
    except Exception as e:
        logger.error(f"Error stopping avatar: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==== Health & Metrics ====

@app.route('/health')
def health():
    realtime_api_ok = bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY)
    speech_service_ok = bool(SPEECH_KEY and SPEECH_REGION)
    minipywo_ok = MINIPYWO_AVAILABLE
    ice_server_ok = bool(ICE_SERVER_URL)
    
    # Check active realtime connections
    active_realtime_connections = len(realtime_connections)

    if MINIPYWO_AVAILABLE:
        try:
            test_config = {"configurable": {"thread_id": "health_check"}}
            test_result = wl_pywo.invoke({"question": "test"}, test_config)
            minipywo_ok = test_result is not None
        except:
            minipywo_ok = False

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
                'model': AZURE_OPENAI_MODEL,
                'active_connections': active_realtime_connections
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
            },
            'proxy': {
                'status': 'healthy',
                'type': 'Socket.IO',
                'active_connections': active_realtime_connections
            }
        },
        'features': {
            'realtime_conversation': realtime_api_ok,
            'avatar_support': realtime_api_ok and speech_service_ok and ENABLE_AVATAR,
            'ypf_knowledge_processing': minipywo_ok,
            'function_calling': minipywo_ok,
            'webrtc_connectivity': ice_server_ok,
            'metrics_enabled': ENABLE_METRICS,
            'proxy_enabled': True
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
            'speech_token': '/api/speech-token',
            'minipywo_process': '/api/minipywo-process',
            'avatar_start': '/api/avatar/start',
            'avatar_stop': '/api/avatar/stop',
            'health_check': '/health',
            'metrics': '/metrics'
        },
        'sessions': {
            'active_count': len(client_sessions),
            'client_ids': list(client_sessions.keys()),
            'realtime_connected': sum(1 for s in client_sessions.values() if s.get('realtime_connected', False))
        }
    }), 200 if status == "healthy" else 503

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

@app.route('/metrics')
def metrics():
    total_messages = sum(len(s['messages']) for s in client_sessions.values())
    total_errors = sum(m.get('errors', 0) for m in session_metrics.values()) if ENABLE_METRICS else 0
    total_realtime_messages = sum(m.get('realtime_messages', 0) for m in session_metrics.values()) if ENABLE_METRICS else 0
    
    metrics_data = {
        'timestamp': datetime.now().isoformat(),
        'application': {
            'name': 'Azure Speech Live Voice with Avatar Server',
            'version': APP_VERSION,
            'environment': os.environ.get('NODE_ENV', 'production')
        },
        'sessions': {
            'total': len(client_sessions),
            'active': len([s for s in client_sessions.values() if len(s['messages']) > 0]),
            'with_avatar': len([s for s in client_sessions.values() if s.get('avatar_state') == 'active']),
            'with_realtime': len(realtime_connections)
        },
        'messages': {
            'total': total_messages,
            'realtime': total_realtime_messages,
            'average_per_session': total_messages / max(len(client_sessions), 1)
        },
        'errors': {
            'total': total_errors,
            'rate': total_errors / max(total_messages, 1) if total_messages > 0 else 0
        },
        'proxy': {
            'active_connections': len(realtime_connections),
            'connection_ids': list(realtime_connections.keys())
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
            'webrtc_max_bitrate': WEBRTC_MAX_BITRATE,
            'proxy_enabled': True
        }
    }
    if ENABLE_METRICS and session_metrics:
        metrics_data['detailed_metrics'] = {
            'sessions': session_metrics,
            'aggregate': {
                'total_message_count': sum(m.get('message_count', 0) for m in session_metrics.values()),
                'total_avatar_frames': sum(m.get('avatar_frames', 0) for m in session_metrics.values()),
                'total_audio_packets': sum(m.get('audio_packets', 0) for m in session_metrics.values()),
                'total_realtime_messages': total_realtime_messages
            }
        }
    return jsonify(metrics_data)

# ==== Socket.IO Events ====

@socketio.on("connect")
def handle_connect():
    client_id = request.args.get('client_id', generate_client_id())
    session = get_or_create_session(client_id)
    logger.info(f"Client connected: {client_id} (sid: {request.sid})")
    
    emit('status', {
        'message': 'Connected to Azure Speech Live Voice with Avatar server',
        'client_id': client_id,
        'features': {
            'avatar': ENABLE_AVATAR,
            'minipywo': MINIPYWO_AVAILABLE,
            'speech_service': bool(SPEECH_KEY),
            'webrtc': bool(ICE_SERVER_URL),
            'realtime_proxy': True
        },
        'configuration': {
            'voice_model': VOICE_MODEL,
            'avatar_character': AVATAR_CHARACTER,
            'language': LANGUAGE
        }
    })

@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"Client disconnected (sid: {request.sid})")
    
    # Limpiar conexiones Realtime si existen
    for client_id, proxy in list(realtime_connections.items()):
        if proxy.sid == request.sid:
            try:
                proxy.close()
                del realtime_connections[client_id]
                logger.info(f"Cleaned up Realtime connection for disconnected client {client_id}")
            except Exception as e:
                logger.error(f"Error cleaning up connection for {client_id}: {e}")

@socketio.on("realtime_status")
def handle_realtime_status(data):
    logger.info(f"Realtime API status: {data}")
    client_id = data.get('client_id')
    if client_id and client_id in client_sessions:
        client_sessions[client_id]['connection_quality'] = data.get('quality', 'unknown')
        client_sessions[client_id]['realtime_connected'] = data.get('connected', False)
        if ENABLE_METRICS and client_id in session_metrics and 'latency' in data:
            session_metrics[client_id]['latency_samples'].append(data['latency'])
    emit('status', {
        'message': f"Realtime API: {data.get('status', 'unknown')}",
        'timestamp': datetime.now().isoformat(),
        'details': data
    })

@socketio.on('process_message')
def handle_process_message(data):
    if not MINIPYWO_AVAILABLE:
        emit('error', {'message': 'minipywo system not available'})
        return
    try:
        user_message = data.get('message', '')
        client_id = data.get('client_id', generate_client_id())
        config = {"configurable": {"thread_id": client_id}}
        corrected_message = replace_token(user_message, original_list, replacement_list)
        result = wl_pywo.invoke({"question": corrected_message}, config)
        response_text = result.get("query_result", "Error processing YPF query")
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
    if ENABLE_METRICS:
        client_id = data.get('client_id')
        if client_id and client_id in session_metrics:
            session_metrics[client_id]['avatar_frames'] += 1

@socketio.on('audio_packet')
def handle_audio_packet(data):
    if ENABLE_METRICS:
        client_id = data.get('client_id')
        if client_id and client_id in session_metrics:
            session_metrics[client_id]['audio_packets'] += 1

# ==== API de prueba ====

@app.route('/api/test-realtime', methods=["POST"])
def test_realtime():
    try:
        data = request.get_json()
        test_message = data.get('message', 'test message')
        active_connections = len(realtime_connections)
        
        return jsonify({
            "status": "success",
            "configuration": {
                "endpoint_configured": bool(AZURE_OPENAI_ENDPOINT),
                "deployment": AZURE_OPENAI_DEPLOYMENT,
                "api_version": AZURE_OPENAI_API_VERSION,
                "model": AZURE_OPENAI_MODEL,
                "avatar_enabled": ENABLE_AVATAR,
                "speech_service": { "configured": bool(SPEECH_KEY), "region": SPEECH_REGION },
                "minipywo_available": MINIPYWO_AVAILABLE,
                "proxy_active": True,
                "active_realtime_connections": active_connections
            },
            "test_input": test_message,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({ "status": "error", "message": str(e) }), 500

# ==== Error handlers ====

@app.errorhandler(404)
def not_found(error):
    return jsonify({ 'error': 'Not found', 'message': 'The requested resource was not found', 'status_code': 404 }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({ 'error': 'Internal server error', 'message': 'An unexpected error occurred', 'status_code': 500 }), 500

# ==== Session cleanup ====

def cleanup_old_sessions():
    try:
        current_time = datetime.now()
        sessions_to_remove = []
        for client_id, session in client_sessions.items():
            last_activity = datetime.fromisoformat(session['last_activity'])
            if (current_time - last_activity).seconds > MAX_SESSION_DURATION:
                sessions_to_remove.append(client_id)
        
        for client_id in sessions_to_remove:
            # Limpiar conexión Realtime si existe
            if client_id in realtime_connections:
                proxy = realtime_connections[client_id]
                proxy.close()
                del realtime_connections[client_id]
            
            client_sessions.pop(client_id, None)
            session_metrics.pop(client_id, None)
            logger.info(f"Cleaned up session: {client_id}")
            
        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")
    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")

def schedule_cleanup():
    cleanup_old_sessions()
    timer = threading.Timer(SESSION_CLEANUP_INTERVAL, schedule_cleanup)
    timer.daemon = True
    timer.start()

# ==== Main ====
if __name__ == "__main__":
    logger.warning("Starting Azure Speech Live Voice with Avatar Server (with Socket.IO Proxy)")
    logger.warning("=" * 60)

    validate_required_environment_variables()

    logger.warning(f"Azure OpenAI Endpoint configured: {bool(AZURE_OPENAI_ENDPOINT)}")
    logger.warning(f"Speech Service Region: {SPEECH_REGION}")
    logger.warning(f"Proxy Mode: Socket.IO WebSocket Proxy")
    
    if ICE_SERVER_URL:
        logger.warning(f"ICE/TURN server configured: {ICE_SERVER_URL}")
    else:
        logger.warning("No ICE/TURN server configured - WebRTC may have connectivity issues")

    logger.warning(f"Avatar support: {ENABLE_AVATAR} ({AVATAR_CHARACTER}/{AVATAR_STYLE}) {AVATAR_RESOLUTION_WIDTH}x{AVATAR_RESOLUTION_HEIGHT}@{AVATAR_VIDEO_FRAMERATE}fps")
    logger.warning(f"Voice: model={VOICE_MODEL} name={VOICE_NAME} lang={LANGUAGE}")
    logger.warning(f"Version: {APP_VERSION}")

    if SESSION_CLEANUP_INTERVAL > 0:
        schedule_cleanup()
        logger.warning(f"Session cleanup scheduled every {SESSION_CLEANUP_INTERVAL}s")

    logger.warning("=" * 60)
    logger.warning(f"Server starting on {FLASK_HOST}:{FLASK_PORT}")
    logger.warning("WebSocket proxy ready for Azure OpenAI Realtime API")

    socketio.run(app, host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)