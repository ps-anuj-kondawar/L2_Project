"""
ChemShield AI — Reflection & Guardrail Agent.

Audits the generated 16-section GHS SDS document for compliance, completeness,
and data integrity. Acts as the final quality gate before the document is delivered.

Checks performed (in order):
  1. Section count — all 16 GHS sections must be present and non-empty
  2. CAS hallucination — CAS numbers in Section 3 are validated against PubChem data
     (with fallback to MASTER_CHEMICAL_DATABASE when PubChem is unavailable)
  3. Section 3 exposure limit leakage — exposure limits belong in Section 8 only
  4. PPE completeness — Section 8 must reference protective equipment
  5. UN transport classification — Section 14 must contain UN number or classification
  6. Statutory regulatory references — Section 15 must cite TSCA, SARA, REACH, or OSHA
  7. Emergency contact — Section 1 must contain emergency contact and responsible party info
  8. Physical properties — Section 9 must contain boiling point, flash point, or vapor pressure
  9. Carcinogen disclosure — if a carcinogen is present, Section 11 must reference IARC or NTP

Fail behavior: any failed check sets reflection_passed=False and adds a note.
The supervisor retries SDS authoring up to 2 times, passing notes back as correction context.
"""

import time
import re
from src.core.state import AgentState
from src.core.logger import logger
from src.core.constants import CAS_TO_NAME, MASTER_CHEMICAL_DATABASE

# Compiled regex patterns
_CAS_PATTERN = re.compile(r"\b\d{2,7}-\d{2}-\d\b")

# Carcinogens that require IARC/NTP disclosure in Section 11
_IARC_GROUP1_CHEMICALS = {"benzene", "formaldehyde", "sulfuric acid"}
_IARC_GROUP2A_CHEMICALS = {"chloroform", "dichloromethane", "methylene chloride"}
_CARCINOGENS_REQUIRING_DISCLOSURE = _IARC_GROUP1_CHEMICALS | _IARC_GROUP2A_CHEMICALS


async def run_reflection_agent(state: AgentState) -> AgentState:
    """
    Reflection & Guardrail Agent entry point.

    Audits state.sds_document against 9 deterministic checks.
    Sets state.reflection_passed and populates state.reflection_notes.

    Args:
        state: Current AgentState containing the generated SDS document.

    Returns:
        Updated AgentState with reflection_passed and reflection_notes set.
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

    # Check 1: All 16 GHS sections must be present
    if len(sds.sections) < 16:
        state.reflection_passed = False
        state.reflection_notes.append(
            f"Incomplete SDS: Found only {len(sds.sections)}/16 sections. "
            f"Missing sections must be authored before delivery."
        )

    # Check 2: CAS number hallucination guard in Section 3
    sec3_content = next((s.content for s in sds.sections if s.section_number == 3), "")
    cas_in_sds = _CAS_PATTERN.findall(sec3_content)

    # Build known CAS set from PubChem data
    known_cas: set[str] = {
        p.get("cas_number")
        for p in state.pubchem_data.values()
        if isinstance(p, dict) and p.get("cas_number") and p.get("cas_number") != "Data not available"
    }

    # Fallback: extend known CAS set from MASTER_CHEMICAL_DATABASE (BUG-5 fix)
    for chem in state.chemicals or []:
        chem_lower = chem.name.lower().strip()
        master_entry = MASTER_CHEMICAL_DATABASE.get(chem_lower)
        if master_entry and master_entry.get("cas_number"):
            known_cas.add(master_entry["cas_number"])

    if cas_in_sds and not known_cas:
        state.reflection_passed = False
        state.reflection_notes.append(
            "CAS numbers found in Section 3 but no PubChem or master database CAS data was available to verify them. "
            "Manual CAS verification required before document delivery."
        )
    elif known_cas:
        hallucinated_cas = [cas for cas in cas_in_sds if cas not in known_cas]
        if hallucinated_cas:
            # Check if they appear in CAS_TO_NAME (might be valid alternatives)
            truly_hallucinated = [cas for cas in hallucinated_cas if cas not in CAS_TO_NAME]
            if truly_hallucinated:
                state.reflection_passed = False
                state.reflection_notes.append(
                    f"Potential CAS hallucination in Section 3: {truly_hallucinated}. "
                    f"These CAS numbers are not in PubChem data or the master chemical database."
                )

    # Check 3: Section 3 must NOT contain exposure limits (they belong in Section 8)
    sec3_upper = sec3_content.upper()
    if any(kw in sec3_upper for kw in ["PEL", "TWA", "STEL", "ACGIH TLV", "OSHA PEL"]):
        state.reflection_passed = False
        state.reflection_notes.append(
            "Section 3 (Composition/Information on Ingredients) incorrectly contains exposure limits. "
            "PEL, TWA, STEL, and TLV values belong exclusively in Section 8 (Exposure Controls/PPE)."
        )

    # Check 4: Section 8 must reference PPE for any hazardous chemicals
    sec8_content = next((s.content for s in sds.sections if s.section_number == 8), "")
    if state.chemical_flags:
        if not any(kw in sec8_content.lower() for kw in ["glove", "respirator", "goggles", "ppe", "protection", "hood", "mask"]):
            state.reflection_passed = False
            state.reflection_notes.append(
                "Section 8 (Exposure Controls/PPE) is missing explicit personal protective equipment requirements. "
                "Gloves, eye protection, and respiratory protection must be specified for hazardous chemicals."
            )

    # Check 5: Section 14 must contain UN number or explicit 'not regulated' classification
    sec14_content = next((s.content for s in sds.sections if s.section_number == 14), "")
    if not any(kw in sec14_content.upper() for kw in ["UN", "NOT REGULATED", "CLASS", "PACKING GROUP"]):
        state.reflection_passed = False
        state.reflection_notes.append(
            "Section 14 (Transport Information) is missing the UN Number, hazard class, "
            "or an explicit 'Not Regulated' declaration. DOT/IATA transport classification is required."
        )

    # Check 6: Section 15 must cite relevant statutory regulatory frameworks
    sec15_content = next((s.content for s in sds.sections if s.section_number == 15), "")
    if not any(kw in sec15_content.upper() for kw in ["TSCA", "SARA", "PROP 65", "PROPOSITION 65", "REACH", "OSHA", "CFR"]):
        state.reflection_passed = False
        state.reflection_notes.append(
            "Section 15 (Regulatory Information) is missing statutory regulatory references. "
            "Must cite applicable regulations such as TSCA, SARA Title III, OSHA standards, "
            "California Proposition 65, or REACH (EU)."
        )

    # Check 7: Section 1 must contain emergency contact information
    # Verifies the DRAFT disclaimer and responsible party placeholder are present.
    # Does not validate a specific phone number format — formatting varies by jurisdiction.
    sec1_content = next((s.content for s in sds.sections if s.section_number == 1), "")
    sec1_upper = sec1_content.upper()
    has_emergency_keyword = (
        "EMERGENCY" in sec1_upper
        or "CHEMTREC" in sec1_upper
        or "POISON" in sec1_upper
        or "HOTLINE" in sec1_upper
    )
    has_responsible_party = (
        "RESPONSIBLE PARTY" in sec1_upper
        or "TO BE COMPLETED" in sec1_upper
        or "DRAFT" in sec1_upper
    )
    if not (has_emergency_keyword and has_responsible_party):
        state.reflection_passed = False
        state.reflection_notes.append(
            "Section 1 (Identification) is missing emergency contact information or responsible party disclaimer. "
            "Must include an emergency contact reference (e.g., CHEMTREC) and a 'DRAFT — [TO BE COMPLETED BY RESPONSIBLE PARTY]' disclaimer per OSHA HazCom 2012."
        )

    # Check 8: Section 9 must contain physical properties relevant to safety
    sec9_content = next((s.content for s in sds.sections if s.section_number == 9), "")
    if not any(kw in sec9_content.lower() for kw in ["boiling", "flash", "vapor pressure", "density", "melting"]):
        state.reflection_passed = False
        state.reflection_notes.append(
            "Section 9 (Physical and Chemical Properties) is missing key safety properties. "
            "Must include boiling point, flash point, and vapor pressure for all hazardous chemicals."
        )

    # Check 9: Carcinogen IARC/NTP disclosure in Section 11
    sec11_content = next((s.content for s in sds.sections if s.section_number == 11), "")
    chem_names_lower = {c.name.lower().strip() for c in (state.chemicals or [])}
    has_carcinogen = bool(chem_names_lower & _CARCINOGENS_REQUIRING_DISCLOSURE)
    if has_carcinogen:
        if not any(kw in sec11_content.upper() for kw in ["IARC", "NTP", "CARCINOGEN", "KNOWN TO CAUSE CANCER"]):
            state.reflection_passed = False
            state.reflection_notes.append(
                "Section 11 (Toxicological Information) is missing carcinogen classification disclosure. "
                "The formulation contains an IARC Group 1 or Group 2A classified carcinogen. "
                "IARC and NTP carcinogen status must be explicitly stated."
            )

    # Check 10: Chemical Cross-Section Consistency Audit (Section 3 Integrity Guard)
    # Ensures chemicals mentioned in Section 3 (Composition/Ingredients) are limited to
    # the actual formulation components. This prevents hallucinated extra chemicals in the
    # ingredient list only — other sections legitimately use generic safety language.
    # Scanning all sections would produce false positives on standard boilerplate text.
    sec3_only = sec3_content.lower()
    unrelated_detected = []
    for db_chem in MASTER_CHEMICAL_DATABASE:
        # Skip formulation chemicals and very short names (acronyms, abbreviations)
        if db_chem in chem_names_lower or len(db_chem) < 6:
            continue
        # Match whole word in Section 3 ingredient list only
        if re.search(r'\b' + re.escape(db_chem) + r'\b', sec3_only):
            unrelated_detected.append(db_chem)

    if unrelated_detected:
        state.reflection_passed = False
        issues_str = ", ".join([f"'{c}'" for c in unrelated_detected[:5]])
        state.reflection_notes.append(
            f"CRITICAL: Section 3 lists chemicals not present in the formulation ({issues_str}). "
            f"Section 3 (Composition/Ingredients) must only contain chemicals extracted from the user input."
        )


    duration = int((time.time() - start_time) * 1000)
    status_str = "passed" if state.reflection_passed else f"failed ({len(state.reflection_notes)} issues)"

    logger.info(f"[ReflectionAgent] Audit complete: {status_str}")
    state.add_trace(
        agent="ReflectionAgent",
        action="GHS Compliance & Guardrail Audit (10 checks)",
        observation=f"Reflection audit {status_str}. Notes: {state.reflection_notes}",
        duration_ms=duration,
        status="success" if state.reflection_passed else "warning"
    )
    return state
