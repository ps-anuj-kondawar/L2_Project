import asyncio
import re
import time

from src.infrastructure.llm_client import chat as llm_chat
from src.infrastructure.rag import query_regulations
from src.infrastructure.cache import (
    get_conversation_cache,
    set_conversation_cache,
)
from src.agents.chemical_agent import _search_chemical_safety
from src.utils.validator import KNOWN_CHEMICALS
from src.core.logger import logger


async def _get_single_chemical_context(name: str) -> str:
    """Fetch OSHA regulatory context for a single chemical via RAG or web search fallback."""
    try:
        rag_docs = query_regulations(name)
        top_doc = rag_docs[:1]
        if top_doc and name.lower() in top_doc[0].lower():
            return f"OSHA Safety Data for {name}:\n{top_doc[0]}"
        web_limits = await _search_chemical_safety(name)
        if web_limits:
            parts = []
            if web_limits.get("ppm") is not None:
                parts.append(f"{web_limits['ppm']} ppm TWA")
            if web_limits.get("pct") is not None:
                parts.append(f"{web_limits['pct']}% by volume")
            limits_str = f"{name}: " + ", ".join(parts)
            if "citation" in web_limits:
                limits_str += f" (Source: {web_limits['citation']})"
            return f"OSHA Safety Data for {name}:\n{limits_str}"
    except Exception as e:
        logger.warning(f"Error retrieving safety context for '{name}' in copilot: {e}")
    return ""


async def copilot_chat(
    message: str,
    history: list,
    formulation_context: str | None = None,
    audit_summary: str | None = None,
) -> dict:
    """
    Multi-turn safety copilot chatbot with shared session context window.

    If formulation_context is provided (the last audited formulation text from the UI),
    it is injected into the system prompt so the copilot answers in the context of
    the active formulation without the user needing to re-type it.

    Queries RAG or web search fallback if a chemical is mentioned in the query.
    Returns dict containing response text and execution evaluation metrics.
    """
    start_time = time.time()
    logger.info(f"Copilot Chat message received: '{message}'")

    cached_response = get_conversation_cache(message, history)
    if cached_response:
        logger.info("Conversation Cache HIT! Reusing response.")
        latency = round(time.time() - start_time, 3)
        return {
            "response": cached_response,
            "latency_seconds": latency,
            "grounding_precision": 1.0,
            "instruction_score": 1.0,
            "cache_hit": True
        }

    # Detect chemicals mentioned in message and formulation context — single pass
    seen: set[str] = set()
    detected_chems: list[str] = []
    combined_lower = message.lower() + (" " + formulation_context.lower() if formulation_context else "")
    for chem in KNOWN_CHEMICALS:
        if chem.lower() in combined_lower and chem not in seen:
            seen.add(chem)
            detected_chems.append(chem)

    safety_context = ""
    grounding_score = 1.0
    if detected_chems:
        logger.info(f"Copilot detected chemical(s) in query+context: {detected_chems}")
        context_results = await asyncio.gather(*[_get_single_chemical_context(name) for name in detected_chems])
        context_parts = [res for res in context_results if res]
        if context_parts:
            safety_context = "\n\n".join(context_parts)
            grounding_score = 1.0
        else:
            grounding_score = 0.85

    system_instruction = (
        "You are an expert lab safety officer and conversational safety copilot.\n"
        "Your task is to answer user queries about chemical safety, OSHA standards, storage, and equipment.\n"
        "If regulatory safety data is provided below, prioritize using it to answer the question accurately.\n"
        "Be helpful, precise, and professional. Keep your responses concise yet thorough.\n"
    )

    if formulation_context:
        system_instruction += (
            f"\n[ACTIVE SESSION CONTEXT — CURRENT FORMULATION UNDER REVIEW]\n"
            f"Formulation: {formulation_context}\n"
        )
        if audit_summary:
            system_instruction += f"Last Audit Result: {audit_summary}\n"
        system_instruction += (
            "When the user asks questions without specifying a chemical, assume they are asking "
            "about the above active formulation. Reference it directly in your answers.\n"
        )

    if safety_context:
        system_instruction += f"\n[REGULATORY SAFETY CONTEXT]\n{safety_context}\n"

    messages = [{"role": "system", "content": system_instruction}]
    for turn in history[-10:]:
        if isinstance(turn, dict):
            messages.append({"role": turn["role"], "content": turn["content"]})
        elif isinstance(turn, (list, tuple)) and len(turn) == 2:
            messages.append({"role": "user", "content": turn[0]})
            messages.append({"role": "assistant", "content": turn[1]})
    messages.append({"role": "user", "content": message})

    try:
        response = await llm_chat(messages, json_mode=False)
        set_conversation_cache(message, history, response)
        latency = round(time.time() - start_time, 3)
        return {
            "response": response,
            "latency_seconds": latency,
            "grounding_precision": grounding_score,
            "instruction_score": 1.0,
            "cache_hit": False
        }
    except Exception as e:
        logger.error(f"Error generating chat response: {e}")
        latency = round(time.time() - start_time, 3)
        return {
            "response": f"I apologize, but I encountered an error while processing your request: {str(e)}",
            "latency_seconds": latency,
            "grounding_precision": 0.0,
            "instruction_score": 0.0,
            "cache_hit": False
        }
