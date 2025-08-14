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


#RagException
class RAGException(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message
        return None
    
    def __str__(self):
        return self.message

# Env variables
AZURE_OPENAI_LOAD_BALANCING = "true" # set to 'false' if you want to turn this off
AZURE_OPENAI_TEMPERATURE = os.environ.get("AZURE_OPENAI_TEMPERATURE") or "0.17"
AZURE_OPENAI_TOP_P = os.environ.get("AZURE_OPENAI_TOP_P") or "0.27"
AZURE_OPENAI_RESP_MAX_TOKENS = os.environ.get("AZURE_OPENAI_MAX_TOKENS") or "1536"
AZURE_OPENAI_LOAD_BALANCING = True if AZURE_OPENAI_LOAD_BALANCING.lower() == "true" else False

AZURE_OPENAI_CHATGPT_MODEL = os.environ.get("AZURE_OPENAI_CHAT_MODEL_NAME")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_EMBEDDING_MODEL = os.environ.get("AZURE_OPENAI_EMBEDDING_MODEL")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")
AZURE_OPENAI_CHATGPT_DEPLOYMENT = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

ORCHESTRATOR_MESSAGES_LANGUAGE = os.environ.get("ORCHESTRATOR_MESSAGES_LANGUAGE") or "es"

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
    def __init__(self, name, level=logging.INFO):
        self.logger=logging.getLogger(name)
        self.logger.propagate=False
        self.logger.setLevel(level)
        if not self.logger.handlers:
            stream_handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('[%(asctime)s][%(levelname)s][%(name)s][%(funcName)s] %(message)s')
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)

logging.getLogger('azure').setLevel(logging.WARNING)
logger=GetLogger(__name__, level=LOGLEVEL).logger

##########################################################
# KEY VAULT 
##########################################################

def get_secret(secret_name):
    retrieved_secret = os.getenv(secret_name)
    return retrieved_secret 

def generate_embeddings(text):
    embeddings_config = get_aoai_config(AZURE_OPENAI_EMBEDDING_MODEL)

    client = AzureOpenAI(
        api_version=embeddings_config['api_version'],
        azure_endpoint=embeddings_config['endpoint'],
        api_key=embeddings_config['api_key'],
    )

    embeddings = client.embeddings.create(input=[text], model=embeddings_config['deployment']).data[0].embedding

    return embeddings

##########################################################
# GPT FUNCTIONS
##########################################################

def number_of_tokens(messages, model):
    prompt = json.dumps(messages)
    encoding = tiktoken.encoding_for_model(model.replace('gpt-35-turbo','gpt-3.5-turbo'))
    num_tokens = len(encoding.encode(prompt))
    return num_tokens

def truncate_to_max_tokens(text, extra_tokens, model):
    max_tokens = model_max_tokens[model] - extra_tokens
    tokens_allowed = max_tokens - number_of_tokens(text, model=model)
    while tokens_allowed < int(AZURE_OPENAI_RESP_MAX_TOKENS) and len(text) > 0:
        text = text[:-1]
        tokens_allowed = max_tokens - number_of_tokens(text, model=model)
    return text

# reduce messages to fit in the model's max tokens
def optmize_messages(chat_history_messages, model): 
    messages = chat_history_messages
    # check each get_sources function message and reduce its size to fit into the model's max tokens
    for idx, message in enumerate(messages):
        if message['role'] == 'function' and message['name'] == 'get_sources':
            # top tokens to the max tokens allowed by the model
            sources = json.loads(message['content'])['sources']

            tokens_allowed = model_max_tokens[model] - number_of_tokens(json.dumps(messages), model=model)
            while tokens_allowed < int(AZURE_OPENAI_RESP_MAX_TOKENS) and len(sources) > 0:
                sources = sources[:-1]
                content = json.dumps({"sources": sources})
                messages[idx]['content'] = content                
                tokens_allowed = model_max_tokens[model] - number_of_tokens(json.dumps(messages), model=model)

    return messages
   
@retry(wait=wait_random_exponential(min=20, max=60), stop=stop_after_attempt(6), reraise=True)
async def call_semantic_function(kernel, function, arguments):
    function_result = await kernel.invoke(function, arguments)
    return function_result

@retry(wait=wait_random_exponential(min=2, max=60), stop=stop_after_attempt(6), reraise=True)
def chat_complete(messages, functions, function_call='auto'):
    """  Return assistant chat response based on user query. Assumes existing list of messages """

    oai_config = get_aoai_config(AZURE_OPENAI_CHATGPT_MODEL)

    messages = optmize_messages(messages, AZURE_OPENAI_CHATGPT_MODEL)

    url = f"{oai_config['endpoint']}/openai/deployments/{oai_config['deployment']}/chat/completions?api-version={oai_config['api_version']}"

    headers = {
        "Content-Type": "application/json",
        "api-key": oai_config['api_key']
        #"Authorization": "Bearer "+ oai_config['api_key'] 
    }

    data = {
        "messages": messages,
        "max_tokens": int(AZURE_OPENAI_RESP_MAX_TOKENS)
    }

    if function_call != 'none' and len(functions) > 0:
        data["functions"] = functions
        data["function_call"] = function_call

    if function_call == 'auto':
        data['temperature'] = 0
    else:
        data['temperature'] = float(AZURE_OPENAI_TEMPERATURE)
        data['top_p'] = float(AZURE_OPENAI_TOP_P) 

    start_time = time.time()
    response = requests.post(url, headers=headers, data=json.dumps(data)).json()
    response_time =  round(time.time() - start_time,2)
    logger.info(f"called chat completion api in {response_time:.6f} seconds")

    return response

##########################################################
# FORMATTING FUNCTIONS
##########################################################

# enforce answer format to the desired format (html, markdown, none)
def format_answer(answer, format= 'none'):
    
    formatted_answer = answer
    
    if format == 'html':
        
        # Convert bold syntax (**text**) to HTML
        formatted_answer = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', formatted_answer)
        
        # Convert italic syntax (*text*) to HTML
        formatted_answer = re.sub(r'\*(.*?)\*', r'<em>\1</em>', formatted_answer)
        
        # Return the converted text
    
    elif format == 'markdown':
        formatted_answer = answer 
    
    elif format == 'none':        
        formatted_answer = answer

    return formatted_answer
  
# replace [doc1] [doc2] [doc3] with the corresponding filepath
def replace_doc_ids_with_filepath(answer, citations):
    for i, citation in enumerate(citations):
        filepath = urllib.parse.quote(citation['filepath'])
        answer = answer.replace(f"[doc{i+1}]", f"[{filepath}]")
    return answer


def escape_xml_characters(input_string):
    """
    Escapes special characters in a string for XML.

    Args:
    input_string (str): The string to escape.

    Returns:
    str: The escaped string.
    """
    # Mapping of special characters to their escaped versions
    escape_mappings = {
        "&": "&amp;",
        "\"": "&quot;",
        "'": "&apos;",
        "<": "&lt;",
        ">": "&gt;"
    }

    # Replace each special character with its escaped version
    for key, value in escape_mappings.items():
        input_string = input_string.replace(key, value)

    return input_string

class TextChange(NamedTuple):
    """Represents a change made to the text"""
    type: str
    original: str
    modified: str

class ReferenceCleaner:
    """Class for cleaning and managing references in texts."""
    
    SUPERSCRIPTS = {
        "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
        "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹"
    }

    MEASUREMENT_UNITS = ['m', 'cm', 'km', 'g', 'kg', 'L', 'mL', 'W', 'kW', 'J', 'cal']

    no_changes_response = "ReferenceCleaner: No changes were made to the text."

    @classmethod
    def is_measurement_superscript(cls, text: str, superscript: str) -> bool:
        """
        Detect if a superscript is part of a measurement, case-insensitively.
        
        Args:
            text (str): The full text containing the superscript
            superscript (str): The superscript to check
        
        Returns:
            bool: True if the superscript is part of a measurement, False otherwise
        """
        # Case-insensitive measurement patterns
        measurement_patterns = [
            # Patterns like "10 cm²", "5 M³"
            fr'\d+\s*(?:{"|".join(cls.MEASUREMENT_UNITS)})(?:\s*{re.escape(superscript)})(?:\s|$|\W)',
            
            # Patterns like "10 Kg/Cm²", "5 W/m³"
            fr'\d+\s*(?:{"|".join(cls.MEASUREMENT_UNITS)})(?:/\w+)?(?:\s*{re.escape(superscript)})(?:\s|$|\W)'
        ]
        
        # Convert text to lowercase for case-insensitive matching
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in measurement_patterns)

    @staticmethod
    def _split_content_references(text: str) -> Tuple[str, str]:
        """Splits the text into content and references."""
        parts = text.split("**Referencias:**")
        if len(parts) != 2:
            return text.strip(), ""
        return parts[0].strip(), parts[1].strip()

    @staticmethod
    def _clean_duplicate_superscripts(group: str) -> Tuple[str, TextChange]:
        """Removes duplicate superscripts in a group."""
        characters = sorted(set(group), key=group.index)
        cleaned = ''.join(characters)
        if cleaned != group:
            return cleaned, TextChange('superscript', group, cleaned)
        return cleaned, None

    def _format_changes_log(self, changes: list[TextChange], before: str) -> str:
        """Formats the list of changes into a human-readable string."""
        if not changes:
            return self.no_changes_response

        log_parts = ["ReferenceCleaner:"]
        hyphens = '-' * 20
        log_parts.append(f"\n{hyphens} Original {hyphens}\n\n{before}")
        log_parts.append(f"\n{hyphens} The following changes were made {hyphens}")

        # Group changes by type
        reference_changes = []
        number_changes = []
        superscript_changes = []
        superscript_removals = []

        for change in changes:
            if change.type == 'reference':
                reference_changes.append(f"- Reference '{change.original}' was {change.modified}")
            elif change.type == 'reference_number':
                number_changes.append(f"- Reference number changed from {change.original} to {change.modified}")
            elif change.type == 'superscript':
                superscript_changes.append(f"- Superscript '{change.original}' was updated to '{change.modified}'")
            elif change.type == 'superscript_removal':
                superscript_removals.append(f"- Removed invalid superscript '{change.original}'")

        # Add each group to the log with headers
        if reference_changes:
            log_parts.append("\nReference merging:")
            log_parts.extend(reference_changes)

        if number_changes:
            log_parts.append("\nReference numbering:")
            log_parts.extend(number_changes)

        if superscript_changes:
            log_parts.append("\nSuperscript updates:")
            log_parts.extend(superscript_changes)

        if superscript_removals:
            log_parts.append("\nInvalid superscript removal:")
            log_parts.extend(superscript_removals)

        changes_log = '\n'.join(log_parts)

        return changes_log + '\n'

    def _process_reference_line(self, line: str) -> Optional[Tuple[int, str, str]]:
        """Processes a reference line and returns (number, full text, unique_identifier)."""
        if not line or not line[0].isdigit():
            return None
            
        match = re.match(r'^(\d+)\.\s*(.+)$', line.strip())
        if not match:
            return None
            
        original_num = int(match.group(1))
        reference_text = match.group(2)
        unique_identifier = reference_text
        return original_num, reference_text, unique_identifier
    
    def _extract_unique_references(self, references: str) -> Tuple[List[str], Dict[str, List[int]], List[TextChange]]:
        """Extracts unique references and creates title to numbers mapping."""
        unique_references = []
        reference_mapping = {}
        changes = []
        
        seen_references = {}  # Track duplicate references
        
        for line in references.split('\n'):
            result = self._process_reference_line(line.strip())
            if not result:
                continue
                
            original_num, reference_text, title = result
            
            if reference_text in seen_references:
                changes.append(TextChange(
                    'reference',
                    f"{original_num}. {reference_text}",
                    f"merged with reference {seen_references[reference_text]}"
                ))
            else:
                seen_references[reference_text] = original_num
                unique_references.append(reference_text)
                
            if title in reference_mapping:
                reference_mapping[title].append(original_num)
            else:
                reference_mapping[title] = [original_num]
                
        return unique_references, reference_mapping, changes
    
    def _create_number_mapping(self, unique_references: List[str], 
                             reference_mapping: Dict[str, List[int]]) -> Tuple[Dict[int, int], List[TextChange]]:
        """Creates mapping from old numbers to new ones and tracks number changes."""
        number_mapping = {}
        changes = []
        
        for i, ref in enumerate(unique_references, 1):
            old_nums = reference_mapping[ref]
            for old_num in old_nums:
                if old_num != i:
                    changes.append(TextChange(
                        'reference_number',
                        str(old_num),
                        str(i)
                    ))
                number_mapping[old_num] = i
                
        return number_mapping, changes
    
    def _update_superscripts(self, content: str, number_mapping: Dict[int, int], 
                           max_references: int) -> Tuple[str, List[TextChange]]:
        """Updates superscripts in the content."""
        new_content = content
        changes = []
        
        # Replace superscripts using the mapping
        for old_num, new_num in number_mapping.items():
            old_superscript = self.SUPERSCRIPTS.get(str(old_num))
            new_superscript = self.SUPERSCRIPTS.get(str(new_num))
            
            # Check if superscript is NOT a measurement unit
            if (old_superscript and new_superscript and 
                old_superscript != new_superscript and 
                not self.is_measurement_superscript(content, old_superscript)):
                new_content = new_content.replace(old_superscript, new_superscript)
                changes.append(TextChange(
                    'superscript',
                    old_superscript,
                    new_superscript
                ))

        # Clean superscript groups, preserving measurements
        superscript_pattern = r'[¹²³⁴⁵⁶⁷⁸⁹]+'
        def clean_group(match):
            group = match.group()
            # Only clean if none of the superscripts are measurements
            if not any(self.is_measurement_superscript(content, s) for s in group):
                cleaned, change = self._clean_duplicate_superscripts(group)
                if change:
                    changes.append(change)
                return cleaned
            return group
            
        new_content = re.sub(superscript_pattern, clean_group, new_content)
        
        # Remove invalid superscripts, except measurements
        for number, superscript in self.SUPERSCRIPTS.items():
            if (int(number) > max_references and 
                superscript in new_content and 
                not self.is_measurement_superscript(new_content, superscript)):
                new_content = new_content.replace(superscript, '')
                changes.append(TextChange(
                    'superscript_removal',
                    superscript,
                    ''
                ))
                
        return new_content, changes
    
    def _format_references(self, unique_references: List[str]) -> str:
        """Formats the final reference list."""
        final_references = "**Referencias:**\n"
        for i, ref in enumerate(unique_references, 1):
            final_references += f"{i}. {ref}\n"

        return final_references
    
    def clean_references(self, text: str) -> Tuple[str, str]:
        """Cleans duplicate references and corrects superscripts in the text.
        
        Returns:
            Tuple containing:
            - The cleaned text
            - A human-readable log of all changes made
        """
        # Initial validation
        if not text or "**Referencias:**" not in text:
            return text, self.no_changes_response

        # Split content and references
        content, references = self._split_content_references(text)
        if not references:
            return text, self.no_changes_response
        
        # Process references
        unique_references, reference_mapping, reference_changes = self._extract_unique_references(references)
        
        # Create number mapping
        number_mapping, number_changes = self._create_number_mapping(unique_references, reference_mapping)
        
        # Update superscripts
        new_content, superscript_changes = self._update_superscripts(
            content, 
            number_mapping, 
            len(unique_references)
        )
        
        # Format references
        final_references = self._format_references(unique_references)

        # Final answer
        final_answer = f"{new_content.strip()}\n\n{final_references.strip()}"
        
        # Combine all changes
        all_changes = (reference_changes + number_changes + superscript_changes)
        
        # Create the changes log
        changes_log = self._format_changes_log(all_changes, text)
        
        return final_answer, changes_log

##########################################################
# MESSAGES FUNCTIONS
##########################################################

def get_cleaned_words(text):
    # Usar una expresión regular para eliminar caracteres especiales
    cleaned_text = re.sub(r'[^\w\s]', '', text)
    return cleaned_text.lower().split()

def get_message(message):
    if ORCHESTRATOR_MESSAGES_LANGUAGE.startswith("pt"):
        messages_file = "webapi/semantic/messages/pt.json"
    elif ORCHESTRATOR_MESSAGES_LANGUAGE.startswith("es"):
        messages_file = "webapi/semantic/messages/es.json"
    else:
        messages_file = "webapi/semantic/messages/en.json"
    with open(messages_file, 'r', encoding='utf-8') as f:
        json_data = f.read()
    messages_dict = json.loads(json_data)
    return messages_dict[message]

def get_last_messages(messages, n):
    """
    This function returns the last n*2 messages from the provided list, including the last message.

    Parameters:
    messages (list): A list of messages.
    n (int): The number of pairs of messages to return.

    Returns:
    list: A list containing the last n*2 messages, including the last message. If the input list is empty, an empty list is returned.

    Note:
    This function assumes that a conversation consists of pairs of messages (a message and a response). Therefore, it returns n*2 messages to get n pairs of messages.
    """    
    # Check if messages is not empty
    if messages and len(messages) >= 1:
        # Get the last N*2 messages (N pairs), including the last message
        last_conversations = messages[-(n*2):]
        return last_conversations
    else:
        return []

##########################################################
# SEMANTIC KERNEL
##########################################################

def load_sk_plugin(name, oai_config):
    kernel = sk.Kernel()
    kernel.add_chat_service("chat_completion", AzureChatCompletion(oai_config['deployment'], oai_config['endpoint'], oai_config['api_key'], ad_auth=True))
    plugin = kernel.import_semantic_skill_from_directory("webapi/semantic/plugins", name)
    native_functions = kernel.import_native_skill_from_directory("webapi/semantic/plugins", name)
    plugin.update(native_functions)
    return plugin

def create_kernel(service_id='aoai_chat_completion'):
    kernel = sk.Kernel()
    chatgpt_config = get_aoai_config(AZURE_OPENAI_CHATGPT_MODEL)
    kernel.add_service(
        AzureChatCompletion(
            service_id=service_id,
            deployment_name=chatgpt_config['deployment'],
            endpoint=chatgpt_config['endpoint'],
            api_version=chatgpt_config['api_version'],
            api_key= chatgpt_config['api_key'],
        )
    )
    return kernel

def get_usage_tokens(function_result, token_type='total'):
    metadata = function_result.metadata['metadata']
    usage_tokens = 0
    if token_type == 'completion':
        usage_tokens = sum(item['usage'].completion_tokens for item in metadata if 'usage' in item)
    elif token_type == 'prompt':
        usage_tokens = sum(item['usage'].prompt_tokens for item in metadata if 'usage' in item)
    elif token_type == 'total':
        usage_tokens = sum(item['usage'].total_tokens for item in metadata if 'usage' in item)        
    return usage_tokens

##########################################################
# AOAI FUNCTIONS
##########################################################

def get_list_from_string(string):
    result = string.split(',')
    result = [item.strip() for item in result]
    return result

def get_aoai_config(model):
    azure_openai_api_key = os.environ.get('AZURE_OPENAI_API_KEY')
    azure_openai_endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT')

    resource = model
    openaikey = azure_openai_api_key
    endpoint = azure_openai_endpoint

    if not openaikey or not endpoint:
        raise RAGException("API key or endpoint not set in environment variables or configuration file")

    if model in ('gpt-35-turbo-16k', 'gpt-4', 'gpt-4o','gpt-4o-mini', 'o1-preview'):
        deployment = AZURE_OPENAI_CHATGPT_DEPLOYMENT
        logger.debug(f"OPENAI DEPLOYMENT: {deployment}")
    elif model == AZURE_OPENAI_EMBEDDING_MODEL:
        deployment = AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME 
    else:
        raise RAGException(f"Model {model} not supported. Check if you have the correct env variables set.")

    result = {
        "resource": resource,
        "endpoint": endpoint,
        "deployment": deployment,
        "model": model,  # ex: 'gpt-35-turbo-16k', 'gpt-4', 'gpt-4-32k'
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION"),
        "api_key": openaikey
    }
    logger.debug(f"get aoai RETURNED: {result}")
    return result
    

##########################################################
# SQL Execute Query Endpoint
##########################################################

def validate_select_query(query: str) -> bool:
    """
    Valida que la consulta sea únicamente SELECT y no contenga subqueries maliciosas
    """
    try:
        # Normalizar la consulta eliminando espacios extras
        formatted_query = ' '.join(query.lower().split())
        
        # Validar punto y coma
        # Permite un único punto y coma al final, elimina espacios después del ;
        if ';' in formatted_query:
            formatted_query = formatted_query.rstrip()
            if not formatted_query.endswith(';'):
                return False
            if formatted_query.count(';') > 1:
                return False
            # Eliminar el punto y coma final para el resto de validaciones
            formatted_query = formatted_query[:-1]
        
        # Parsear la consulta con sqlparse
        parsed = sqlparse.parse(formatted_query)[0]
        
        # Verificar que el primer token sea SELECT
        if parsed.get_type() != 'SELECT':
            return False
            
        # Buscar palabras clave prohibidas
        dangerous_keywords = [
            r'\bdelete\b', r'\bupdate\b', r'\binsert\b',
            r'\bdrop\b', r'\btruncate\b', r'\balter\b',
            r'\bcreate\b', r'\breplace\b', r'\bmerge\b',
            r'\bcopy\b', r'\bgrant\b', r'\brevoke\b'
        ]
        
        pattern = '|'.join(dangerous_keywords)
        if re.search(pattern, formatted_query):
            return False
            
        return True
        
    except Exception as e:
        print(f"Error validando query: {str(e)}")  # Para debugging
        return False

def enforce_row_limit(query: str, max_rows: int) -> str:
    """
    Asegura que la consulta tenga un LIMIT y que no exceda max_rows
    """
    formatted_query = ' '.join(query.lower().split())
    
    # Remover punto y coma final si existe
    if formatted_query.rstrip().endswith(';'):
        formatted_query = formatted_query.rstrip()[:-1]
    
    # Buscar si ya existe un LIMIT en la consulta
    limit_match = re.search(r'\blimit\s+(\d+)', formatted_query)
    
    if limit_match:
        # Si existe un LIMIT, asegurarse que no exceda max_rows
        current_limit = int(limit_match.group(1))
        if current_limit > max_rows:
            # Reemplazar el LIMIT existente
            new_query = re.sub(r'\blimit\s+\d+', f'limit {max_rows}', formatted_query)
            return f"{new_query};"
        return f"{formatted_query};"
    else:
        # Si no existe LIMIT, agregarlo al final
        return f"{formatted_query} limit {max_rows};"

def execute_query_with_timeout(db, query: str, timeout_seconds: int):
    """
    Ejecuta la consulta con un timeout usando ThreadPoolExecutor
    """
    def _execute():
        result = db.execute(text(query))
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result]

    test_query = text("SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE query_start < now() - :valor")
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_execute)
        try:
            rows = future.result(timeout=timeout_seconds)
            return rows
        except TimeoutError:
            # Intentar cancelar la consulta si es posible
            try:
                db.execute(test_query,{"valor":timeout_seconds})
            except Exception as e:
                print(f"Error ejecutando query: {str(e)}")
            raise

##########################################################
# OTHER FUNCTIONS
##########################################################

def get_blocked_list():
    blocked_list = [
        "abuso", "assault", "asesinato", "murder", "bomba", "bomb", "corrupción", "corruption", "crimen", "crime",
        "droga", "drug", "estafa", "scam", "fraude", "fraud", "guerra", "war", "hackeo", "hacking", "odio", "hate",
        "pedofilia", "pedophilia", "pornografía", "pornography", "racismo", "racism", "robo", "theft", "terrorismo", 
        "terrorism", "tortura", "torture", "violación", "rape", "violencia", "violence", "xenofobia", "xenophobia",
        "armas", "weapons", "prostitución", "prostitution", "acoso", "harassment", "maltrato", "abuse", "discriminación",
        "discrimination", "genocidio", "genocide", "killing", "lynching", "extortion", "extorsión", "trafficking", 
        "tráfico", "hostage", "rehén", "kidnapping", "secuestro", "shooting", "tiroteo"
    ]
    blocked_list = [word.lower() for word in blocked_list]
    return blocked_list

def extract_text_from_html(url):
    try:
        html_response = requests.get(url)
        html_response.raise_for_status()
        soup = BeautifulSoup(html_response.text, 'html.parser')
        for tag in soup.find_all('header'):
            tag.decompose()
        for tag in soup.find_all('footer'):
            tag.decompose()
        for tag in soup.find_all('form'):
            tag.decompose()
        # Extract visible text from the HTML
        texts = soup.stripped_strings
        visible_text = ' '.join(texts)
        html_response.close()
        return visible_text
    except Exception as e:
        logger.error(f"Failed to extract text from HTML: {e}")
        raise
    
def get_possitive_int_or_default(var, default_value):
    try:
        var = int(var)
        if var < 0:
            var = default_value
    except Exception:
        var = default_value
    return var