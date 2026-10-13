"""
ChemShield AI — Chemical Safety Copilot Engine.

Provides multi-turn conversational safety assistance with:
- Automated entity and CAS number recognition in chat prompts
- Grounded RAG retrieval against OSHA standards and PubChem databases
- Context injection for active formulation audits and compliance findings
- Session-based conversation caching for low-latency responses
"""

import asyncio
import re
import time

from src.agents.chemical_agent import _search_chemical_safety
from src.core.constants import CAS_TO_NAME, MASTER_CHEMICAL_DATABASE
from src.core.logger import logger
from src.infrastructure.cache import (
    get_conversation_cache,
    set_conversation_cache,
)
from src.infrastructure.llm_client import chat as llm_chat
from src.utils.validator import KNOWN_CHEMICALS

# Detect CAS Registry Numbers typed into the chat (e.g., "71-43-2", "7664-93-9")
_CAS_IN_TEXT_PATTERN = re.compile(r'\b(\d{2,7}-\d{2}-\d)\b')


async def _get_single_chemical_context(name: str) -> str:
    """
    Fetch OSHA regulatory and exposure limit context for a single chemical.

    Checks MASTER_CHEMICAL_DATABASE first, falling back to Tavily live web search.

    Args:
        name (str): Canonical or common chemical name.

    Returns:
        str: Formatted OSHA safety data string with source citations, or empty string on error.
    """
    try:
        norm_name = name.lower().strip()
        if norm_name in MASTER_CHEMICAL_DATABASE:
            entry = MASTER_CHEMICAL_DATABASE[norm_name]
            parts = []
            if entry.get("pel_ppm") is not None:
                parts.append(f"{entry['pel_ppm']} ppm TWA")
            if entry.get("liquid_pct_limit") is not None:
                parts.append(f"{entry['liquid_pct_limit']}% by volume")
            limits_str = f"{name}: " + ", ".join(parts) + " (Source: OSHA Master Database)"
            return f"OSHA Safety Data for {name}:\n{limits_str}"

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
    Execute a multi-turn safety copilot conversation turn.

    Injects active formulation context and prior audit findings into the system prompt,
    performs entity detection and CAS resolution on chat inputs, and retrieves
    authoritative safety data to ground the LLM response.

    Args:
        message (str): Current user query or prompt.
        history (list): List of previous message dictionaries in chronological order.
        formulation_context (str | None): Active lab formulation note for contextual awareness.
        audit_summary (str | None): Summary sentence from the latest compliance audit run.

    Returns:
        dict: Response dictionary containing 'response', 'latency_seconds', 'grounding_precision',
              'instruction_score', and 'cache_hit' indicators.
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

    # Detect chemicals by name from message and formulation context
    seen: set[str] = set()
    detected_chems: list[str] = []
    combined_lower = message.lower() + (" " + formulation_context.lower() if formulation_context else "")
    for chem in KNOWN_CHEMICALS:
        if chem.lower() in combined_lower and chem not in seen:
            seen.add(chem)
            detected_chems.append(chem)

    # Also resolve any CAS numbers typed directly in the message (e.g., "71-43-2")
    for cas_match in _CAS_IN_TEXT_PATTERN.finditer(message):
        cas_num = cas_match.group(1)
        resolved_name = CAS_TO_NAME.get(cas_num)
        if resolved_name and resolved_name not in seen:
            logger.info(f"[Copilot] CAS number '{cas_num}' in chat resolved to '{resolved_name}'")
            seen.add(resolved_name)
            detected_chems.append(resolved_name.title())

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
            "response": f"I apologize, but I encountered an error while processing your request: {e!s}",
            "latency_seconds": latency,
            "grounding_precision": 0.0,
            "instruction_score": 0.0,
            "cache_hit": False
        }
