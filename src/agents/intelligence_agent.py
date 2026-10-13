import asyncio
import time

from src.core.logger import logger
from src.core.state import AgentState
from src.infrastructure.pubchem_client import get_pubchem_data


async def run_intelligence_agent(state: AgentState) -> AgentState:
    """
    PubChem & Regulatory Intelligence Agent.
    Fetches CAS numbers, GHS hazard codes, signal words, and physical properties
    concurrently for all chemicals in state.chemicals.
    """
    start_time = time.time()
    # Step 1: Early return if no chemical entities are present in state
    if not state.chemicals:
        state.add_trace(
            agent="IntelligenceAgent",
            action="PubChem & GHS Data Fetch",
            observation="No chemicals to query in state.",
            duration_ms=int((time.time() - start_time) * 1000),
            status="success"
        )
        return state

    chem_names = [c.name for c in state.chemicals]
    logger.info(f"[IntelligenceAgent] Fetching PubChem data for {len(chem_names)} chemicals: {chem_names}")

    # Step 2: Concurrent async fetch across all chemicals (uses PubChem REST client + SQLite cache)
    results = await asyncio.gather(*[get_pubchem_data(name) for name in chem_names])

    # Step 3: Populate shared blackboard state with PubChem data dictionaries
    for chem_data in results:
        state.pubchem_data[chem_data.chemical_name.lower().strip()] = chem_data.model_dump()

    duration = int((time.time() - start_time) * 1000)
    found_cids = [d.cid for d in results if d.cid]

    # Step 4: Record execution trace for UI streaming and auditing
    state.add_trace(
        agent="IntelligenceAgent",
        action=f"PubChem REST API Query ({len(chem_names)} chemicals)",
        observation=f"Retrieved PubChem data. Found CIDs: {found_cids}",
        duration_ms=duration,
        status="success"
    )
    return state
