# ChemShield AI — Agent Decision Trace Reference

This document explains the multi-agent ReAct (Reasoning + Acting) loop that powers ChemShield AI. It is intended for developers who need to understand how the system reaches its compliance verdicts.

---

## Architecture Overview

ChemShield AI uses a **Supervisor** that orchestrates a set of specialized agents. The supervisor runs a bounded ReAct loop (max 8 iterations) and dispatches agents based on the action the language model selects. A safety guardrail layer enforces that critical checks (chemical, hardware, PubChem) always run, even if the model attempts to skip them.

```
User Input → Supervisor → ReAct Loop → [Agents] → Verdict + SDS → Response
```

---

## Agent Inventory

| Agent | Module | Responsibility |
|-------|--------|---------------|
| `EntityExtractor` | `supervisor.py:_extract_entities` | Parses chemicals, CAS numbers, concentrations, and hardware from unstructured text |
| `ChemicalComplianceAgent` | `agents/chemical_agent.py` | 5-layer regulatory limit lookup (Master DB → RAG → Cache → Gemini → Tavily) |
| `HardwareComplianceAgent` | `agents/hardware_agent.py` | MCP stdio thermal safety check → web fallback for unknown equipment |
| `PubChemIntelligenceAgent` | `agents/intelligence_agent.py` | PubChem API fetch: CAS numbers, GHS pictograms, molecular weight, hazard statements |
| `SDSAuthorAgent` | `agents/sds_author_agent.py` | Authors all 16 GHS sections using formulation data, PubChem data, and regulatory limits |
| `ReflectionAgent` | `agents/reflection_agent.py` | 9-point audit of the generated SDS document for quality, completeness, and compliance |

---

## ReAct Loop — Action Vocabulary

The Supervisor LLM can select the following actions each iteration:

| Action String | Triggers | Effect |
|---------------|----------|--------|
| `check_chemical_compliance` | When chemicals are present in extracted entities | Runs `ChemicalComplianceAgent` |
| `check_hardware_compatibility` | When hardware items are present in extracted entities | Runs `HardwareComplianceAgent` |
| `fetch_pubchem_intelligence` | When chemicals need GHS data for SDS authoring | Runs `PubChemIntelligenceAgent` |
| `author_sds_document` | When all safety checks are complete and SDS is needed | Runs `SDSAuthorAgent` + `ReflectionAgent` |
| `finish_audit` | When all required checks are done | Exits the ReAct loop |

---

## Decision Trace Example — Benzene Formulation

```
Input: "94% Water, 6% Benzene. Heated to 120°C in a soda-lime glass beaker."
```

**Extracted entities:**
- Chemicals: Benzene (6%), Water (94%)
- Hardware: Soda-lime glass beaker @ 120°C

**Step 1 → ChemicalComplianceAgent**
- Checks Benzene 6% vs OSHA liquid limit 0.1% → NON_COMPLIANT
- Checks Water → COMPLIANT (no limit)
- Retrieval source: `master_db` (hardcoded, authoritative)

**Step 2 → HardwareComplianceAgent**
- MCP call: `check_hardware_compatibility("soda-lime glass beaker", 120.0)`
- Response: max_safe_temp = 100°C, is_safe = False → UNSAFE

**Step 3 → PubChemIntelligenceAgent**
- Fetches CAS 71-43-2, MW=78.11, GHS: H225, H302, H350
- Signal word: DANGER (H350 = carcinogen)

**Step 4 → SDSAuthorAgent**
- Authors 16 GHS sections with above data
- Includes: IARC Group 1 carcinogen disclosure in Section 11
- Includes: UN1114 Benzene Solution transport info in Section 14

**Step 5 → ReflectionAgent**
- Check 1: 16/16 sections ✓
- Check 2: CAS 71-43-2 verified in MASTER_CHEMICAL_DATABASE ✓
- Check 3: Section 3 has no exposure limits ✓
- Check 4: Section 8 references gloves, fume hood, goggles ✓
- Check 5: Section 14 has UN1114 ✓
- Check 6: Section 15 cites TSCA, OSHA ✓
- Check 7: Section 1 has CHEMTREC 1-800-424-9300 ✓
- Check 8: Section 9 has boiling point 80.1°C, flash point ✓
- Check 9: Section 11 references IARC Group 1 carcinogen ✓
- Result: reflection_passed = True

**Final verdict: NON_COMPLIANT (Benzene > limit + soda-lime glass UNSAFE)**

---

## Safety Guardrail Layer

The guardrail runs after the ReAct loop finishes. It enforces that certain checks always happen even if the model chose `finish_audit` prematurely:

1. **Chemical guardrail**: If `chemical` not in completed actions → force `ChemicalComplianceAgent`
2. **Hardware guardrail**: If `hardware` not in completed actions → force `HardwareComplianceAgent`
3. **PubChem guardrail**: If `pubchem` not in completed actions → force `PubChemIntelligenceAgent`

Guardrail-enforced steps are tagged with `action_source: "guardrail_override"` in the trace, distinguishing them from `"model_selected"` steps.

---

## Fail-Closed Philosophy

Every default in the system is fail-closed:

| Scenario | Old (buggy) behavior | New behavior |
|----------|---------------------|--------------|
| Chemical with no regulatory data | `COMPLIANT` (bug) | `UNKNOWN` |
| Concentration not specified | `COMPLIANT` (bug) | `REVIEW_REQUIRED` |
| Units incompatible (% vs ppm) | Wrong comparison result | `REVIEW_REQUIRED` with explanation |
| Stale cache with ppm=None | Used as "0 ppm" (bug) | Cache bypassed, fresh lookup |
| ChemicalFlag default status | `COMPLIANT` (Pydantic default) | `REVIEW_REQUIRED` |
| HardwareFlag default status | `SAFE` (Pydantic default) | `REVIEW_REQUIRED` |

**The principle**: A positive evidence of compliance is required to emit `COMPLIANT`. Absence of data never implies safety.

---

## Trace Log Format

Each trace step is a `TraceStep` model:

```python
TraceStep(
    agent="ChemicalComplianceAgent",
    action="OSHA Regulatory Limit Check (3 chemicals, 5-layer retrieval)",
    observation="Evaluated 3 chemicals. Non-compliant: ['Benzene']",
    timestamp_ms=1722480234123,
    duration_ms=1840,
    status="warning",       # "success" | "warning" | "error"
    action_source="model_selected"  # or "guardrail_override"
)
```

The `action_source` field allows the Agent Trace view in the frontend to show a red **Guardrail** badge on steps that were safety-policy-enforced rather than AI-selected.

---

## Reflection Agent — 9 Quality Checks

| Check # | What is Checked | Failure Action |
|---------|-----------------|----------------|
| 1 | All 16 GHS sections present | Fail + re-author |
| 2 | CAS numbers in Section 3 match PubChem or master DB | Fail + flag for manual review |
| 3 | Section 3 contains no exposure limits (wrong section) | Fail + correction note |
| 4 | Section 8 references PPE (gloves, respirator, goggles) | Fail + correction note |
| 5 | Section 14 contains UN number or "Not Regulated" | Fail + correction note |
| 6 | Section 15 cites TSCA, SARA, REACH, or OSHA | Fail + correction note |
| 7 | Section 1 has emergency telephone and responsible party | Fail + correction note |
| 8 | Section 9 has boiling point, flash point, or vapor pressure | Fail + correction note |
| 9 | If carcinogen present, Section 11 cites IARC or NTP | Fail + correction note |

The Supervisor retries SDS authoring up to 2 times, passing all reflection notes as correction context to the SDSAuthorAgent.
