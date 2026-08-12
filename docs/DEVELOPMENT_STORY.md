# ChemShield AI — Development Story

*This document is the living chronicle of ChemShield AI's creation: what we thought, why we changed it, what we got wrong, and what we learned.*

---

## Chapter 1: The Problem Statement (Initial Design)

### What We Set Out to Build

The original idea was simple: a chatbot that could answer questions like "is this formulation OSHA-compliant?" without requiring a user to manually search through 29 CFR 1910.1000 tables. The first version was a RAG (Retrieval-Augmented Generation) pipeline — embed regulatory text, then retrieve relevant chunks when asked about a chemical.

**The problem**: RAG retrieval is inherently imprecise. A chunk retrieved for "acetone exposure limit" sometimes contained toluene values from adjacent table rows. The system would emit a confident answer citing the wrong chemical's limits.

### Why a Multi-Agent Architecture?

After early testing, we realized that the problem wasn't just lookup — it was orchestration:

1. **Entity extraction**: The user says "6% benzen in water at 120°C" — we need to extract the chemical name (with typo correction), concentration, and temperature.
2. **Chemical safety evaluation**: Look up the OSHA limit for that chemical in the right region.
3. **Hardware safety evaluation**: Separately, check if the container can handle the temperature.
4. **GHS document authoring**: If all of that passes (or fails), produce a professionally-structured SDS.
5. **Quality assurance**: Verify the generated SDS meets GHS standards before delivery.

No single LLM call could do all of this reliably. We moved to a **ReAct (Reasoning + Acting) multi-agent architecture** where a Supervisor LLM decides which specialized agent to invoke at each step.

---

## Chapter 2: Building the Core Pipeline

### The First MCP Experiment

The hardware safety check was the first agent we built. The question "can this container handle the temperature?" is deterministic — it doesn't need a language model. We implemented a **FastMCP server** that exposes a single tool: `check_hardware_compatibility(equipment_name, temperature)`. The hardware agent calls this tool over stdio transport.

**What we learned**: MCP key matching was brittle. A user input of "Borosilicate Glass Beaker" (capitalized) would fail to match "borosilicate glass beaker" in the dictionary. We added normalized key matching (lowercase + substring match) in the MCP server to handle variations.

### The Chemical Agent's Journey

The chemical agent went through five architectural iterations:

**v1 (Tavily only)**: Query Tavily for every chemical, extract the PEL from search results. **Problem**: Too slow (~4 seconds per chemical), inconsistent result quality, and PubChem pages sometimes contained misleading threshold values from different jurisdictions.

**v2 (RAG only)**: Use ChromaDB embeddings of OSHA text. **Problem**: The OSHA regulatory text is terse and table-formatted; chunk boundaries cut through limit values. Retrieval worked for common chemicals but failed for less-covered ones.

**v3 (RAG + cache)**: Cache successful lookups in SQLite. **Problem**: We discovered a critical bug — the cache stored "empty" entries (ppm=None) as a signal that no limit was found, but the cache-reading code treated this as a valid "no limit exists" result, defaulting the chemical to COMPLIANT. A false-COMPLIANT verdict for a hazardous chemical is exactly the worst possible failure mode.

**v4 (master DB + RAG + cache)**: Hardcode authoritative limits for common chemicals in `MASTER_CHEMICAL_DATABASE`. These are always checked first and never overridden by the cache. **Problem**: The coverage was still limited to ~10 chemicals, and Gemini was underutilized.

**v5 (current)**: Five-tier retrieval — Master DB → RAG → cache (with stale-entry bypass) → Gemini direct knowledge → Tavily. This gives fast O(1) answers for the 22 most common OSHA-regulated chemicals, while retaining web-search coverage for exotic compounds.

### The Fail-Closed Discovery

A code review revealed that both `ChemicalFlag` and `HardwareFlag` Pydantic models had default values of `status = "COMPLIANT"` and `status = "SAFE"` respectively. This meant that if an evaluation code path encountered an unexpected branch and returned without setting the status, the model would silently default to a passing result.

**This is a dangerous bug in a chemical safety system.** We changed the defaults to `"REVIEW_REQUIRED"` — the fail-safe position. A positive evidence of compliance is now required to emit a COMPLIANT verdict.

---

## Chapter 3: The GHS SDS Challenge

### 16 Sections and Reflection

GHS mandates a specific 16-section structure for Safety Data Sheets. The SDSAuthorAgent generates all 16 sections in a single LLM call. The first problem we encountered was LLM "hallucination" of CAS numbers — the model would sometimes generate plausible-sounding but incorrect CAS numbers in Section 3 (Composition).

We built a **ReflectionAgent** as the quality gate. It runs 9 automated checks on every generated SDS:

The most technically interesting check was **CAS hallucination detection** (Check 2): compare every CAS number in Section 3 against PubChem data. But PubChem sometimes returns unavailable data — which would cause the reflection to incorrectly flag the correct CAS number as hallucinated.

**Fix**: If PubChem returns no CAS data, fall back to `MASTER_CHEMICAL_DATABASE` as the CAS validation source. This was the BUG-5 fix.

### Signal Word Determination

GHS signal words (DANGER or WARNING) are determined by the worst-case hazard category among all ingredients. The logic was:

```python
if any chemical has signal_word == "DANGER":
    return "DANGER"
```

**Bug**: When PubChem returned `signal_word = None` (data unavailable), calling `.upper()` on None caused an `AttributeError` crash. The system crashed instead of gracefully defaulting to WARNING.

**Fix**: `sig = (chem_data.get("signal_word") or "").upper()` — the `or ""` coerces None to empty string before `.upper()`.

---

## Chapter 4: Review Cycles and What They Taught Us

Five external code reviews were conducted between August 5–11, 2026. Here is what each one found and how we responded:

### Review 1 (Aug 5): "Fail-open logic is unacceptable"

> *"The system defaults to COMPLIANT when no regulatory data is found. In a safety-critical domain, this inverts the expected behavior — unknown should never mean safe."*

**Action**: Changed all default statuses to `REVIEW_REQUIRED`. Introduced the concept of "fail-closed" as a design principle throughout the codebase.

### Review 2 (Aug 6): "NoneType errors in GHS signal word logic"

> *"AttributeError crash when signal_word is None. System crashes on PubChem data fetch failures."*

**Action**: Added `or ""` guard in `determine_overall_signal_word()`. Added null checks throughout PubChem data handling.

### Review 3 (Aug 7): "CAS hallucination vulnerability"

> *"The reflection agent trusts the LLM-generated CAS numbers when PubChem data is unavailable, missing the opportunity to validate against the regulatory database."*

**Action**: Added `MASTER_CHEMICAL_DATABASE` as the CAS fallback validation source in the reflection agent.

### Review 4 (Aug 8): "Documentation-implementation gap"

> *"The ARCHITECTURE.md file is marked 'PARTIAL' and doesn't reflect the actual 5-tier retrieval strategy. Documentation that lags behind implementation is worse than no documentation."*

**Action**: Updated ARCHITECTURE.md, created CHEMICAL_KNOWLEDGE.md, AGENT_DECISION_TRACE.md, REGULATORY_DATA_SOURCES.md, and PRODUCT_OVERVIEW.md. Adopted a policy that any significant implementation change must be reflected in documentation in the same PR.

### Review 5 (Aug 11): "Chemical knowledge score is lowest"

> *"The chemical compliance logic is the most critical component but has the thinnest implementation. Regulatory limits should be cited to specific CFR sections. Unit semantics (ppm vs %) are not clearly documented."*

**Action**: 
- Expanded `MASTER_CHEMICAL_DATABASE` from 8 to 22 chemicals, each with `cas_number`, `standard` (CFR citation), and all 4 limit types
- Added detailed unit semantics documentation in CHEMICAL_KNOWLEDGE.md
- Added Gemini API as a direct chemical knowledge lookup tier (faster than web search)
- Added IARC carcinogen database with explicit Group 1/2A classifications

---

## Chapter 5: What Is Left to Do

The system is functional and production-aware, but several capabilities remain on the roadmap:

1. **Mixture exposure limit calculation**: OSHA defines an additive formula for combined exposure when multiple regulated chemicals are present simultaneously. ChemShield currently evaluates chemicals individually; the combined mixture limit check is not yet implemented.

2. **REACH SVHC lookup**: The EU REACH Substances of Very High Concern (SVHC) candidate list is not yet queried.

3. **SDS versioning**: Each generated SDS should be assigned a version number and stored with a revision timestamp. Currently, each audit generates a new SDS without tracking revisions.

4. **Batch audit**: Users with large chemical portfolios need to audit multiple formulations at once. The current API only handles one formulation per request.

5. **Action level monitoring trigger**: When a chemical's detected level exceeds the OSHA action level (50% of PEL), OSHA mandates air monitoring. ChemShield detects but does not yet emit a structured "action level exceeded" alert separate from the non-compliant verdict.

---

## Design Principles We Carry Forward

1. **Fail-closed, not fail-open**: In a chemical safety system, an error must never be mistaken for compliance.

2. **Hardcoded limits over dynamic data for critical chemicals**: Regulatory limits for well-known chemicals should be in source code, not in a database that can be corrupted by a bad API response.

3. **Unit semantics matter**: ppm (airborne) and % (liquid formulation) are fundamentally different physical quantities. Never compare them without explicit acknowledgment of the unit mismatch.

4. **Every limit needs a citation**: A regulatory limit without a CFR section number or IARC monograph reference is just a guess. ChemShield requires every limit to cite its source.

5. **The document is for a human expert to review**: The SDS generated by ChemShield AI is a first draft. It is clearly marked as AI-generated and requires review by a licensed CSP before regulatory use.
