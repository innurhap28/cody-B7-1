"""One server-side Codyssey request in the explicitly configured API style."""

import httpx


class AITimeoutError(Exception):
    """The upstream service did not answer before the configured deadline."""


class AIServiceError(Exception):
    """The upstream service could not provide a usable answer."""


class AIAuthenticationError(AIServiceError):
    """The provider rejected the server credential (HTTP 401)."""


class AIAccessDeniedError(AIServiceError):
    """The provider refused the chat request (HTTP 403)."""


class AIRateLimitError(AIServiceError):
    """Codyssey returned HTTP 429; the caller should wait before retrying."""


AIError = AIServiceError


async def ask_llm(system: str, messages: list[dict]) -> str:
    """Send one request. Never expose the provider key to the browser."""
    from app.config import settings

    key = settings.LLM_API_KEY.strip()
    if not key:
        raise AIServiceError("LLM_API_KEY is not configured")

    model = settings.LLM_MODEL.strip()
    base_url = settings.LLM_BASE_URL.rstrip("/")
    try:
        timeout = float(settings.LLM_TIMEOUT_SECONDS)
        if timeout <= 0:
            raise ValueError
    except ValueError as exc:
        raise AIServiceError("LLM_TIMEOUT_SECONDS must be positive") from exc
    if settings.LLM_API_STYLE == "anthropic":
        endpoint = "messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        payload = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": settings.LLM_MAX_COMPLETION_TOKENS,
        }
    else:
        endpoint = "chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
            "max_completion_tokens": settings.LLM_MAX_COMPLETION_TOKENS,
        }
        if settings.LLM_JSON_MODE:
            payload["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/{endpoint}",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise AITimeoutError from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise AIAuthenticationError("Codyssey authentication failed") from None
        if exc.response.status_code == 403:
            raise AIAccessDeniedError("Codyssey denied chat access") from None
        if exc.response.status_code == 429:
            raise AIRateLimitError("Codyssey rate limit") from None
        raise AIServiceError("AI request failed") from None
    except httpx.HTTPError as exc:
        raise AIServiceError("AI request failed") from exc

    try:
        data = response.json()
        if settings.LLM_API_STYLE == "anthropic":
            if data.get("stop_reason") == "max_tokens":
                raise AIServiceError("AI response was truncated")
            if data.get("stop_reason") not in {"end_turn", "stop_sequence"}:
                raise AIServiceError("AI response did not complete a text turn")
            blocks = data["content"]
            if not isinstance(blocks, list) or any(not isinstance(b, dict) for b in blocks):
                raise AIServiceError("AI response has an unexpected shape")
            texts = [b["text"] for b in blocks if b.get("type") == "text"]
            if any(not isinstance(text, str) for text in texts):
                raise AIServiceError("AI response has an unexpected shape")
            # Thinking and other non-text blocks never become user-visible output.
            answer = "".join(texts)
        else:
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise AIServiceError("AI response was truncated")
            answer = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AIServiceError("AI response has an unexpected shape") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise AIServiceError("AI response is empty")
    return answer.strip()
