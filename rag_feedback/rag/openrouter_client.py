"""OpenRouter LLM provider for StandardSense."""

from __future__ import annotations

import logging
import os

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-4o-mini",
)

OPENROUTER_TIMEOUT = float(
    os.getenv("OPENROUTER_TIMEOUT", "30")
)


class OpenRouterError(RuntimeError):
    """Raised when an OpenRouter request fails."""


def generate_text(prompt: str) -> str:
    """Generate text using OpenRouter's OpenAI-compatible API."""

    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        logger.error(
            "OpenRouter configuration error: "
            "OPENROUTER_API_KEY is not set"
        )
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not configured"
        )

    client = OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=OPENROUTER_TIMEOUT,
        max_retries=0,
        default_headers={
            "HTTP-Referer": (
                "https://github.com/mj-creates/standard-sense"
            ),
            "X-Title": "StandardSense",
        },
    )

    try:
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.2,
        )

    except RateLimitError as exc:
        logger.error(
            "OpenRouter rate limit exceeded (HTTP 429)"
        )
        raise OpenRouterError(
            "OpenRouter rate limit exceeded"
        ) from exc

    except APITimeoutError as exc:
        logger.error(
            "OpenRouter request timed out after %ss",
            OPENROUTER_TIMEOUT,
        )
        raise OpenRouterError(
            "OpenRouter request timed out"
        ) from exc

    except APIConnectionError as exc:
        logger.error(
            "OpenRouter connection failed: %s",
            exc,
        )
        raise OpenRouterError(
            "Could not connect to OpenRouter"
        ) from exc

    except APIStatusError as exc:
        if exc.status_code in (401, 403):
            logger.error(
                "OpenRouter authentication failed "
                "(HTTP %s): check OPENROUTER_API_KEY",
                exc.status_code,
            )
            raise OpenRouterError(
                "OpenRouter API key is invalid or unauthorized"
            ) from exc

        logger.error(
            "OpenRouter API error (HTTP %s): %s",
            exc.status_code,
            exc.message,
        )
        raise OpenRouterError(
            f"OpenRouter API error (HTTP {exc.status_code})"
        ) from exc

    except Exception as exc:
        logger.error(
            "Unexpected OpenRouter error: %s",
            exc,
        )
        raise OpenRouterError(
            "Unexpected OpenRouter error"
        ) from exc

    if (
        not response.choices
        or not response.choices[0].message.content
    ):
        logger.error(
            "OpenRouter returned an empty response"
        )
        raise OpenRouterError(
            "OpenRouter returned an empty response"
        )

    return response.choices[0].message.content.strip()