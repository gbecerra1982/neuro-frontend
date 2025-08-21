import json
import logging
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Dict, List, NamedTuple, Optional, Tuple

import requests
import semantic_kernel as sk
import sqlparse
import tiktoken
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from bs4 import BeautifulSoup
from openai import AzureOpenAI
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_random_exponential

LOGLEVEL = os.environ.get('LOGLEVEL_UTIL', 'INFO').upper()

model_max_tokens = {
    'gpt-35-turbo': 4096,
    'gpt-35-turbo-16k': 16384,
    'gpt-4': 8192,
    'gpt-4-32k': 32768,
    'gpt-4o': 128000,
    'gpt-4o-mini': 128000, 
    'o1-preview': 128000
}

##########################################################
# LOGGING 
##########################################################

class GetLogger:
    def __init__(self, name, level=logging.INFO, log_file=None):
        self.logger=logging.getLogger(name)
        self.logger.propagate=False
        self.logger.setLevel(level)
        if not self.logger.handlers:
            stream_handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('[%(asctime)s][%(levelname)s][%(name)s][%(funcName)s] %(message)s')
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

        if log_file:
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)