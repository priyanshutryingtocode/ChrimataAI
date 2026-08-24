from __future__ import annotations

from app.core.config import settings


def get_gemini_client():
    api_key = settings.llm_api_key.strip()
    if not api_key:
        return None
    from google import genai

    return genai.Client(api_key=api_key)
