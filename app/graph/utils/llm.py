import asyncio
from langchain_ollama import ChatOllama
from app.config import get_settings

_settings = get_settings()
llm_semaphore = asyncio.Semaphore(_settings.llm_max_concurrency)


def get_llm():
    return ChatOllama(model=_settings.local_llm)
