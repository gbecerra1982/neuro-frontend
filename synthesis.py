#!/usr/bin/env python
import json
import logging
import os
import sys
import time
import uuid
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
import requests

# Configuración de logs
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="[%(asctime)s] %(message)s", datefmt="%m/%d/%Y %I:%M:%S %p %Z")
logger = logging.getLogger(__name__)

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuraciones
SPEECH_ENDPOINT = os.getenv('SPEECH_ENDPOINT')
SPEECH_KEY = os.getenv('SPEECH_KEY')
PASSWORDLESS_AUTHENTICATION = os.getenv('PASSWORDLESS_AUTHENTICATION', 'True').lower() == 'true'
API_VERSION = os.getenv('API_VERSION', '2024-10-01')

# Validar configuraciones obligatorias
if not SPEECH_ENDPOINT:
    raise ValueError("SPEECH_ENDPOINT is not set in the environment or .env file.")
if not PASSWORDLESS_AUTHENTICATION and not SPEECH_KEY:
    raise ValueError("SPEECH_KEY is required when PASSWORDLESS_AUTHENTICATION is disabled.")

logger.info(f"SPEECH_ENDPOINT: {SPEECH_ENDPOINT}")
logger.info(f"PASSWORDLESS_AUTHENTICATION: {PASSWORDLESS_AUTHENTICATION}")
logger.info(f"API_VERSION: {API_VERSION}")

def _create_job_id():
    return uuid.uuid4()

def _authenticate():
    if PASSWORDLESS_AUTHENTICATION:
        credential = DefaultAzureCredential()
        token = credential.get_token('https://cognitiveservices.azure.com/.default')
        return {'Authorization': f'Bearer {token.token}'}
    else:
        return {'Ocp-Apim-Subscription-Key': SPEECH_KEY}

def get_url(endpoint: str):
    return f"{SPEECH_ENDPOINT}{endpoint}?api-version={API_VERSION}"

def submit_synthesis(job_id: str):
    url = get_url(f'/avatar/batchsyntheses/{job_id}')
    header = {'Content-Type': 'application/json'}
    header.update(_authenticate())

    payload = {
        'synthesisConfig': {"voice": "es-AR-TomasNeural"},
        'inputKind': "SSML",
        'inputs': [{
            "content": """<speak xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="es-AR">
                            <voice name="es-AR-TomasNeural">
                                <prosody rate="+15%">Eres un asistente corporativo de la empresa de energia YPF llamado Neuro. Se breve y profesional ayudando a las preguntas o consultas que pueda tener el usuario.</prosody>
                            </voice>
                        </speak>"""
        }],
        'avatarConfig': {
            "customized": True,
            "talkingAvatarCharacter": "Max",
            "talkingAvatarStyle": "business",
            "videoFormat": "mp4",
            "videoCodec": "h264",
            "subtitleType": "soft_embedded",
            "backgroundColor": "#FFFFFFFF"
            #"backgroundImage": "https://img.genial.ly/5ee36284023b9b11bb48c34a/38fd3954-43f7-4a69-9ee6-6fe74b386e14.jpeg"
        }
    }

    response = requests.put(url, json.dumps(payload), headers=header)
    if response.status_code < 400:
        logger.info('Batch avatar synthesis job submitted successfully')
        logger.info(f'Job ID: {response.json()["id"]}')
        return True
    else:
        logger.error(f'Failed to submit batch avatar synthesis job: [{response.status_code}], {response.text}')
        return False

def get_synthesis(job_id):
    url = get_url(f'/avatar/batchsyntheses/{job_id}')
    header = _authenticate()
    response = requests.get(url, headers=header)
    if response.status_code < 400:
        status = response.json()['status']
        logger.info(f'Job status: {status}')
        if status == 'Succeeded':
            logger.info(f'Result: {response.json()["outputs"]["result"]}')
        return status
    else:
        logger.error(f'Failed to get job: {response.text}')

if __name__ == '__main__':
    job_id = _create_job_id()
    if submit_synthesis(job_id):
        while True:
            status = get_synthesis(job_id)
            if status in ['Succeeded', 'Failed']:
                break
            time.sleep(5)
