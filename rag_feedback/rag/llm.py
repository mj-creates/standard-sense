"""
llm.py
------
LLM client initialization for the StandardSense RAG explanation module.
Configures and returns a ChatGroq instance using Groq models.
"""

from __future__ import annotations

import os

import truststore

# Inject system certificate truststore into ssl before initializing HTTP clients
truststore.inject_into_ssl()

from dotenv import load_dotenv
from langchain_groq import ChatGroq

# Load environment variables from .env file
load_dotenv()


def get_llm() -> ChatGroq:
    """
    Initialize and return a ChatGroq language model client.

    Retrieves the GROQ_API_KEY from environment variables and configures
    the ChatGroq model with 'openai/gpt-oss-20b' at temperature 0.

    Returns
    -------
    ChatGroq
        Configured LangChain ChatGroq instance.

    Raises
    ------
    RuntimeError
        If GROQ_API_KEY is missing or empty.
    """
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Please add it to the .env file.")

    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0,
        groq_api_key=api_key,
    )
