from langchain_openai import AzureChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

os.environ['HTTPS_PROXY'] = 'http://proxy-azure:80'
# Asigna la clave estándar al nombre esperado por el SDK
os.environ['AZURE_OPENAI_API_KEY'] = os.getenv('AZURE_OPENAI_STANDARD_API_KEY')
os.environ['AZURE_OPENAI_ENDPOINT'] = os.getenv('AZURE_OPENAI_STANDARD_ENDPOINT')

llm_gpt_4o = AzureChatOpenAI(
        openai_api_version="2024-10-21",
        azure_deployment="chat4og",
        model_name="gpt-4o",
        seed=42)

llm_gpt_4o_mini = AzureChatOpenAI(
        openai_api_version="2025-01-01-preview",
        azure_deployment="gpt-4o-mini",
        model_name="gpt-4o-mini",
        seed=42)

llm_gpt_o3_mini = AzureChatOpenAI(
        openai_api_version="2025-01-01-preview",
        azure_deployment="o3-mini",
        model_name="o3-mini",
        temperature= 1,
        seed=42)

llm_gpt_4_1_mini = AzureChatOpenAI(
        openai_api_version="2025-01-01-preview",
        azure_deployment="gpt-4.1-mini",
        model_name="gpt-4.1-mini",
        seed=42,
        temperature=0.7,
        top_p=0.95)