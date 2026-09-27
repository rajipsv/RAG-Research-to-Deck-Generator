"""Gemini client — chat/generation calls for query expansion and synthesis."""

from __future__ import annotations

import os
import time

from google import genai
from google.genai import errors, types

MODEL = "gemini-3.8-flash"
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 5.0
RETRYABLE_CODES = {429, 500, 503, 504}  # rate limit + transient server errors

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def generate_text(
    prompt: str,
    system_instruction: str | None = None,
    max_output_tokens: int = 2000,
    json_mode: bool = False,
) -> str:
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json" if json_mode else None,
    )
    backoff = INITIAL_BACKOFF_SECONDS
    for attempt in range(MAX_RETRIES):
        try:
            response = get_client().models.generate_content(
                model=MODEL,
                contents=prompt,
                config=config,
            )
            return response.text
        except errors.APIError as e:
            if e.code not in RETRYABLE_CODES or attempt == MAX_RETRIES - 1:
                raise
            time.sleep(backoff)
            backoff *= 2
