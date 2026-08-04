import asyncio
import time
import re
import os
import json
from tavily import TavilyClient
from src.core.state import AgentState
from src.core.models import ChemicalFlag
from src.infrastructure.rag import query_regulations
from src.infrastructure.cache import get_osha_limits, set_osha_limits
from src.core.constants import BOILING_POINTS_CELSIUS
from src.core.logger import logger
from src.infrastructure.llm_client import chat as llm_chat


def _parse_limits(rag_docs: list[str]) -> dict:
    combined = " ".join(rag_docs)
    limits: dict = {}

    ppm_m = re.search(r'(\d+(?:\.\d+)?)\s*ppm\s*TWA', combined, re.IGNORECASE)
    if ppm_m:
        limits["ppm"] = float(ppm_m.group(1))

    pct_m = re.search(r'(\d+(?:\.\d+)?)%\s*by volume', combined, re.IGNORECASE)
    if pct_m:
        limits["pct"] = float(pct_m.group(1))

    src_m = re.search(r'Source:\s*(.+)', combined)
    limits["citation"] = src_m.group(1).strip() if src_m else combined[:200]

    return limits


_TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
_tavily_client: TavilyClient | None = TavilyClient(api_key=_TAVILY_API_KEY) if _TAVILY_API_KEY else None


def _search_chemical_text_sync(chemical_name: str) -> tuple[str, str]:
    if not _tavily_client:
        return "", ""
    try:
        query = (
            f"{chemical_name} OSHA TWA permissible exposure limit ppm boiling point "
            f"site:osha.gov OR site:pubchem.ncbi.nlm.nih.gov OR site:cdc.gov"
        )
        results = _tavily_client.search(query=query, max_results=3)
        combined_text = " ".join(
            str(r.get("raw_content") or r.get("content") or "") for r in results.get("results", [])
        )
        source_url = results["results"][0]["url"] if results.get("results") else ""
        return combined_text, source_url
    except Exception as e:
        logger.warning(f"[ChemicalAgent] Tavily search failed for '{chemical_name}': {e}")
        return "", ""


async def _search_chemical_safety(chemical_name: str) -> dict:
    combined_text, source_url = await asyncio.to_thread(_search_chemical_text_sync, chemical_name)
    if not combined_text:
        return {}
    
    schema = {
        "ppm": "float or null (OSHA TWA/PEL permissible exposure limit in ppm)",
        "pct": "float or null (OSHA volume percentage limit if any)",
        "boiling_point": "float or null (Boiling point in Celsius)",
    }
    prompt = (
        f"Analyze the safety search results for the chemical '{chemical_name}' and extract:\n"
        "1. The OSHA Permissible Exposure Limit (PEL) or TWA in parts per million (ppm).\n"
        "2. The OSHA liquid volume percentage limit (if any).\n"
        "3. The boiling point of the chemical in Celsius.\n\n"
        f"Search Results:\n{combined_text[:3000]}\n\n"
        f"Return ONLY valid JSON matching this schema: {json.dumps(schema)}\n"
        "Use raw floats or null only."
    )
    try:
        raw = await llm_chat(
            messages=[
                {"role": "system", "content": "You are a precise scientific data extractor. Return JSON only."},
                {"role": "user",   "content": prompt},
            ],
            json_mode=True,
        )
        data = json.loads(raw)
        return {
            "ppm": float(data["ppm"]) if data.get("ppm") is not None else None,
            "pct": float(data["pct"]) if data.get("pct") is not None else None,
            "boiling_point": float(data["boiling_point"]) if data.get("boiling_point") is not None else None,
            "citation": f"Web search: {source_url}" if source_url else "Web search query"
        }
    except Exception:
        return {}


async def check_single_chemical(name: str, conc_str: str) -> tuple[ChemicalFlag, bool]:
    if name.lower() == "water":
        return ChemicalFlag(
            chemical_name=name,
            is_compliant=True,
            detected_concentration=conc_str,
            regulatory_limit="No OSHA exposure limit",
            source_citation="Water is not a regulated hazardous substance under OSHA."
        ), True

    is_relevant = False
    try:
        rag_docs = query_regulations(name)
        top_doc = rag_docs[:1]
        if top_doc:
            is_relevant = name.lower() in top_doc[0].lower()
    except Exception:
        top_doc = []

    is_l1_cached = bool(get_osha_limits(name))

    limits = {}
    if not top_doc or not is_relevant:
        web_limits = await _search_chemical_safety(name)
        if web_limits and (web_limits.get("ppm") is not None or web_limits.get("pct") is not None):
            limits = web_limits
            set_osha_limits(name, web_limits)
            is_relevant = True
        else:
            return ChemicalFlag(
                chemical_name=name,
                is_compliant=False,
                detected_concentration=conc_str,
                regulatory_limit="Unknown: No regulatory data found",
                source_citation=""
            ), False
    else:
        limits = _parse_limits(top_doc)
        set_osha_limits(name, limits)

    citation = limits.get("citation", "")
    is_pct = conc_str and "%" in conc_str
    is_ppm = conc_str and "ppm" in conc_str.lower()

    try:
        conc_val = float(re.search(r'[\d.]+', conc_str).group())
    except (AttributeError, ValueError, TypeError):
        conc_val = None

    is_compliant = True
    regulatory_limit = "See OSHA regulations"

    if is_pct and limits.get("pct") is not None and conc_val is not None:
        regulatory_limit = f"{limits['pct']}% by volume (max)"
        is_compliant = conc_val <= limits["pct"]
    elif is_pct and limits.get("ppm") is not None:
        regulatory_limit = f"{int(limits['ppm'])} ppm TWA (airborne, not applicable to liquid volume %)"
        is_compliant = True
    elif is_ppm and limits.get("ppm") is not None and conc_val is not None:
        regulatory_limit = f"{int(limits['ppm'])} ppm TWA"
        is_compliant = conc_val <= limits["ppm"]
    elif limits.get("ppm") is not None:
        regulatory_limit = f"{int(limits['ppm'])} ppm TWA"

    return ChemicalFlag(
        chemical_name=name,
        is_compliant=is_compliant,
        detected_concentration=conc_str,
        regulatory_limit=regulatory_limit,
        source_citation=citation
    ), is_relevant


async def run_chemical_agent(state: AgentState) -> AgentState:
    """
    Chemical Compliance Agent.
    Evaluates all extracted chemicals concurrently against OSHA limits and PubChem data.
    """
    start_time = time.time()
    if not state.chemicals:
        state.add_trace(
            agent="ChemicalComplianceAgent",
            action="Chemical Safety Audit",
            observation="No chemicals found in user input.",
            duration_ms=int((time.time() - start_time) * 1000),
            status="success"
        )
        return state

    logger.info(f"[ChemicalAgent] Evaluating {len(state.chemicals)} chemicals concurrently...")
    tasks = [check_single_chemical(c.name, c.concentration or "") for c in state.chemicals]
    results = await asyncio.gather(*tasks)

    flags = [res[0] for res in results]
    state.chemical_flags = flags

    non_compliant = [f.chemical_name for f in flags if not f.is_compliant]
    obs = f"Evaluated {len(flags)} chemicals. Non-compliant: {non_compliant if non_compliant else 'None'}"

    state.add_trace(
        agent="ChemicalComplianceAgent",
        action=f"OSHA Regulatory Limit Check ({len(flags)} chemicals)",
        observation=obs,
        duration_ms=int((time.time() - start_time) * 1000),
        status="warning" if non_compliant else "success"
    )
    return state
