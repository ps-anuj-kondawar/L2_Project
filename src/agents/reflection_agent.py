import time
import re
from src.core.state import AgentState
from src.core.logger import logger

# Compiled regex patterns
_CAS_PATTERN = re.compile(r"\b\d{2,7}-\d{2}-\d\b")
_PHONE_PATTERN = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")


async def run_reflection_agent(state: AgentState) -> AgentState:
    """
    Reflection & Guardrail Agent.
    Audits the generated SDS document for GHS compliance, section completeness,
    and CAS number hallucinations.
    """
    start_time = time.time()
    logger.info("[ReflectionAgent] Auditing generated SDS document...")

    state.reflection_notes = []
    state.reflection_passed = True

    if not state.sds_document:
        state.reflection_passed = False
        state.reflection_notes.append("No SDS document generated to audit.")
        state.add_trace(
            agent="ReflectionAgent",
            action="GHS Quality & Guardrail Audit",
            observation="Audit failed: SDS Document missing.",
            duration_ms=int((time.time() - start_time) * 1000),
            status="error"
        )
        return state

    sds = state.sds_document

    # Check 1: 16 Sections Present and non-empty
    if len(sds.sections) < 16:
        state.reflection_passed = False
        state.reflection_notes.append(f"Incomplete SDS: Found only {len(sds.sections)}/16 sections.")

    # Check 2: CAS Hallucination check in Section 3
    sec3_content = next((s.content for s in sds.sections if s.section_number == 3), "")
    cas_in_sds = _CAS_PATTERN.findall(sec3_content)
    known_cas = {
        p.get("cas_number")
        for p in state.pubchem_data.values()
        if isinstance(p, dict) and p.get("cas_number") and p.get("cas_number") != "Data not available"
    }

    if cas_in_sds and not known_cas:
        state.reflection_passed = False
        state.reflection_notes.append(
            "CAS numbers found in Section 3 but no reference PubChem CAS data was available to verify them. "
            "Manual CAS verification required."
        )
    elif known_cas:
        hallucinated_cas = [cas for cas in cas_in_sds if cas not in known_cas]
        if hallucinated_cas:
            state.reflection_passed = False
            state.reflection_notes.append(f"Potential CAS hallucination detected in Section 3: {hallucinated_cas}")

    # Check 3: Section 3 Exposure Limit Leakage (Exposure limits belong ONLY in Section 8)
    sec3_upper = sec3_content.upper()
    if any(kw in sec3_upper for kw in ["PEL", "TWA", "STEL", "ACGIH TLV", "OSHA PEL"]):
        state.reflection_passed = False
        state.reflection_notes.append("Section 3 (Composition) contains exposure limits. Exposure limits belong strictly in Section 8.")

    # Check 4: Section 8 PPE and Exposure Limit Presence
    sec8_content = next((s.content for s in sds.sections if s.section_number == 8), "")
    if state.chemical_flags:
        if not any(kw in sec8_content.lower() for kw in ["glove", "respirator", "goggles", "ppe", "protection", "hood"]):
            state.reflection_passed = False
            state.reflection_notes.append("Section 8 missing explicit PPE guidelines for non-compliant or hazardous chemicals.")

    # Check 5: Section 14 Transport UN Number Presence
    sec14_content = next((s.content for s in sds.sections if s.section_number == 14), "")
    if not any(kw in sec14_content.upper() for kw in ["UN", "NOT REGULATED", "CLASS"]):
        state.reflection_passed = False
        state.reflection_notes.append("Section 14 missing official UN Number or transport classification.")

    # Check 6: Section 15 Regulatory References
    sec15_content = next((s.content for s in sds.sections if s.section_number == 15), "")
    if not any(kw in sec15_content.upper() for kw in ["TSCA", "SARA", "PROP 65", "PROPOSITION 65", "REACH", "OSHA"]):
        state.reflection_passed = False
        state.reflection_notes.append("Section 15 missing statutory regulatory references (TSCA, SARA Title III, or Prop 65).")

    # Check 7: Section 1 Manufacturer / Supplier Info
    sec1_content = next((s.content for s in sds.sections if s.section_number == 1), "")
    sec1_upper = sec1_content.upper()
    has_emergency = ("EMERGENCY" in sec1_upper or "CHEMTREC" in sec1_upper) and (
        "RESPONSIBLE PARTY" in sec1_upper or _PHONE_PATTERN.search(sec1_content) is not None
    )
    if not has_emergency:
        state.reflection_passed = False
        state.reflection_notes.append("Section 1 missing emergency telephone hotline contact information or responsible party disclaimer.")

    duration = int((time.time() - start_time) * 1000)
    status_str = "passed" if state.reflection_passed else f"failed ({len(state.reflection_notes)} issues)"

    logger.info(f"[ReflectionAgent] Audit complete: {status_str}")
    state.add_trace(
        agent="ReflectionAgent",
        action="GHS Compliance & Guardrail Audit",
        observation=f"Reflection audit {status_str}. Notes: {state.reflection_notes}",
        duration_ms=duration,
        status="success" if state.reflection_passed else "warning"
    )
    return state
