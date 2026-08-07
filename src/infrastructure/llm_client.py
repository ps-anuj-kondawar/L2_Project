import os
import json
import contextvars
import httpx
from google import genai
from google.genai import types
from dotenv import load_dotenv
from src.core.logger import logger

load_dotenv(override=True)

LLM_PROVIDER      = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
OPENROUTER_MODEL  = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_MAX_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "4096"))

# ContextVar for thread-safe, request-isolated provider tracking
_last_provider_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("_last_provider_ctx", default="Google Gemini")

# Module-level lazy singleton for GenAI client reuse
_genai_client: genai.Client | None = None


def get_last_provider_used() -> str:
    """Return the LLM provider used in the current context/thread."""
    return _last_provider_ctx.get()


# Backward-compatible property shim
class _ProviderTracker:
    def __str__(self) -> str:
        return get_last_provider_used()

    def __repr__(self) -> str:
        return get_last_provider_used()


LAST_PROVIDER_USED = _ProviderTracker()


def _get_genai_client() -> genai.Client:
    global _genai_client
    if _genai_client is None:
        use_vertex = os.getenv("VERTEX_AI", "false").lower() in ("true", "1")
        if use_vertex:
            project_id = os.getenv("GCP_PROJECT_ID")
            location = os.getenv("GCP_LOCATION", "us-central1")
            _genai_client = genai.Client(vertexai=True, project=project_id, location=location)
        else:
            _genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _genai_client


async def chat(messages: list[dict], json_mode: bool = False) -> str:
    """Send messages to LLM and handle transient provider failures with automatic fallback."""
    provider = LLM_PROVIDER
    gemini_key = os.getenv("GEMINI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if provider == "gemini" and gemini_key:
        try:
            res = await _gemini_chat(messages, json_mode)
            _last_provider_ctx.set("Google Gemini")
            return res
        except Exception as e:
            if openrouter_key:
                logger.warning(f"Gemini call failed ({type(e).__name__}: {str(e)}). Falling back to OpenRouter...")
                try:
                    res = await _openrouter_chat(messages, json_mode)
                    _last_provider_ctx.set("OpenRouter (Fallback)")
                    return res
                except Exception as ore:
                    logger.error(f"OpenRouter fallback also failed ({type(ore).__name__}): {ore}")
                    raise ore
            raise e

    if openrouter_key:
        res = await _openrouter_chat(messages, json_mode)
        _last_provider_ctx.set("OpenRouter")
        return res
    elif gemini_key:
        res = await _gemini_chat(messages, json_mode)
        _last_provider_ctx.set("Google Gemini")
        return res
    
    raise ValueError("Neither GEMINI_API_KEY nor OPENROUTER_API_KEY is configured in the environment.")


async def _gemini_chat(messages: list[dict], json_mode: bool) -> str:
    client = _get_genai_client()

    config = types.GenerateContentConfig(
        temperature=0.0,
        max_output_tokens=4096,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
    if system_msg:
        config.system_instruction = system_msg
    
    contents = []
    for m in messages:
        if m["role"] == "system":
            continue
        role = "model" if m["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))
    
    if not contents:
        contents = [types.Content(role="user", parts=[types.Part(text="")])]
    
    async with client.aio as aclient:
        response = await aclient.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        )
    raw_text = response.text if (response and hasattr(response, "text") and response.text) else ""
    result = raw_text.strip().replace("\u202f", " ").replace("\xa0", " ").replace("\u2011", "-")
    logger.info(f"[Gemini Response]: {result}")
    return result


async def _openrouter_chat(messages: list[dict], json_mode: bool) -> str:
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": OPENROUTER_MAX_TOKENS,
    }
    # Omit response_format parameter on OpenRouter free tier to ensure compatibility across all free models
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers, json=payload, timeout=10.0
        )
    resp.raise_for_status()
    raw_content = resp.json()["choices"][0]["message"].get("content")
    content = raw_content.strip().replace("\u202f", " ").replace("\xa0", " ").replace("\u2011", "-") if raw_content else ""
    
    # Gracefully clean up markdown code block formatting if JSON mode was requested
    if json_mode:
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
    logger.info(f"[OpenRouter Response]: {content}")
    return content
