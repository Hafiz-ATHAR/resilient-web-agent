from langchain_ollama import ChatOllama
from app.config import get_settings


def get_llm():
    return ChatOllama(model=get_settings().local_llm)
