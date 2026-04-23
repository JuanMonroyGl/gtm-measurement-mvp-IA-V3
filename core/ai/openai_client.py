"""OpenAI client bootstrap."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurada en el entorno/.env.")
    return OpenAI(api_key=api_key)
