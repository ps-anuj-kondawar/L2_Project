# ChemShield AI - System Workflow & Lifecycle Specifications

This document outlines the detailed execution workflow, dataflow sequence, and state transitions of the ChemShield AI multi-agent platform.

---

## 1. End-to-End Workflow Diagram

```
+-----------------------------------------------------------------------------------+
| 1. USER INPUT                                                                     |
| "Formula A-1: 94% Water, 6% Benzene. Heated to 50C in borosilicate glass beaker."  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 2. FASTAPI ENDPOINT (/api/v1/stream)                                             |
| Parses query params: intent="audit_and_sds", region="US", language="en"           |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 3. SUPERVISOR STEP 0: CACHE AUDIT                                                 |
| Computes SHA-256 hash. If HIT: returns cached result immediately.                 |
+-----------------------------------------------------------------------------------+
                                         | (CACHE MISS)
                                         v
+-----------------------------------------------------------------------------------+
| 4. SUPERVISOR STEP 1: ENTITY EXTRACTION & FUZZY CORRECTION                        |
| LLM parses chemicals: ["Water (94%)", "Benzene (6%)"]                             |
| LLM parses hardware: ["borosilicate glass beaker (50.0C)"]                        |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 5. STEP 2: MODEL-MEDIATED ReAct ACTION LOOP                                       |
|                                                                                   |
|  Decide (Policy LLM) -> Act (Specialist Agent) -> Observe -> Repeat/Finish        |
|  Specialist Agents: IntelligenceAgent, ChemicalComplianceAgent, HardwareAgent      |
|  FastMCP Tool Discovery & Execution over stdio transport                          |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 6. SUPERVISOR STEP 3: SAFETY VERDICT COMPUTATION                                  |
| Evaluates flags against OSHA PELs & hardware thresholds.                          |
| Verdict: REJECTED (6% Benzene exceeds OSHA 0.1% limit).                           |
| LLM synthesizes 1-sentence safety summary.                                        |
+-----------------------------------------------------------------------------------+
                                         |
                       [ intent == "audit_and_sds" or "sds" ]
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 7. SUPERVISOR STEP 4: GHS SDS AUTHORING AGENT                                     |
| Synthesizes 16-section GHS Safety Data Sheet tailored to region (US OSHA)       |
| and target language (English).                                                    |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 8. SUPERVISOR STEP 5: REFLECTION AGENT QA AUDIT                                   |
| Validates GHS document structural completeness and safety disclosures.            |
| Status: PASSED                                                                    |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| 9. SUPERVISOR STEP 6: OUTPUT RENDERING & CACHE STORE                              |
| Renders Jinja2 HTML SDS template.                                                 |
| Saves run result to SQLite input_cache.                                           |
| Streams final JSON & SSE end event to Client UI.                                  |
+-----------------------------------------------------------------------------------+
```

---

## 2. Intent Dispatch Matrix

The Supervisor dynamically tailors execution paths based on the requested `intent`:

| Intent | Extracted Entities | Executed Agents | SDS Authoring | Avg Latency |
| :--- | :--- | :--- | :--- | :--- |
| `audit` | Chemicals & Hardware | Intelligence, Chemical, Hardware | Skipped | ~1.0 sec |
| `sds` | Cached state re-used | Skipped (if cached) | Executed | ~1.5 sec |
| `audit_and_sds` | Chemicals & Hardware | Intelligence, Chemical, Hardware | Executed | ~2.5 sec |

---

## 3. Real-Time Telemetry & Event Streaming (SSE)

During pipeline execution, the FastAPI server streams real-time Server-Sent Events over HTTP using the following event envelope format:

```json
{
  "event": "step_update",
  "data": {
    "step": 2,
    "agent": "ChemicalComplianceAgent",
    "action": "OSHA Regulatory Limit Check",
    "status": "success",
    "duration_ms": 320,
    "observation": "Evaluated 2 chemicals. Non-compliant: ['Benzene']"
  }
}
```

The right-hand sidebar telemetry panel in [index.html](file:///c:/L2_Project/static/index.html) and [app.js](file:///c:/L2_Project/static/app.js) listens to these events to update the 4-stage progress indicators and live trace terminal in real time.

---

## 4. Error Handling & Fallback Matrix

1. **PubChem REST API Failure**: Falls back to local cached chemical records or default GHS Rev.9 pictogram rules (`GHS07`).
2. **ChromaDB Vector Unindexed**: Dispatches live Tavily Web Search API query to retrieve OSHA exposure limit documentation from official web sources (`osha.gov`, `pubchem.ncbi.nlm.nih.gov`, `cdc.gov`).
3. **FastMCP Server Disconnect**: Falls back to in-memory local hardware limit table (`HARDWARE_LIMITS`).
4. **LLM Generation Timeout**: Falls back to structured rule-based section templates to ensure the user always receives a valid, schema-compliant 16-section SDS document.

---

## 6. Chemical Compliance Decision Tree

The following flowchart describes the exact decision path for each chemical evaluated by the `ChemicalComplianceAgent`:

```
For each chemical in formulation:
  │
  ├─ Is chemical == "water"?
  │    YES → Status: COMPLIANT (no regulatory limit for water)
  │    NO  ↓
  │
  ├─ Check MASTER_CHEMICAL_DATABASE (Tier 1)
  │    HIT → use hardcoded PEL/PCT (authoritative, not overridable by cache)
  │    MISS ↓
  │
  ├─ Query ChromaDB RAG (Tier 2)
  │    HIT (chemical name in chunk) → parse PEL/PCT, cache result
  │    MISS ↓
  │
  ├─ Check SQLite cache (Tier 3)
  │    HIT (ppm != None) → use cached limit
  │    MISS or ppm=None (stale entry) ↓
  │
  ├─ Gemini API chemical knowledge lookup (Tier 4)
  │    HIT → parse confirmed limit, cache result
  │    MISS ↓
  │
  ├─ Tavily web search + LLM extraction (Tier 5)
  │    HIT → parse extracted limit, cache result
  │    MISS ↓
  │
  └─ Status: UNKNOWN (fail-closed — no data = not safe)
```

**Compliance evaluation after data retrieval:**

```
If limit found:
  │
  ├─ Concentration missing or empty?
  │    YES → Status: REVIEW_REQUIRED (cannot evaluate without a concentration)
  │
  ├─ Input unit = "%" AND limit unit = "%"?
  │    YES → Direct comparison → COMPLIANT / NON_COMPLIANT
  │
  ├─ Input unit = "%" AND only ppm limit available?
  │    YES → Status: REVIEW_REQUIRED (units incompatible)
  │          ppm = airborne exposure; % = liquid formulation — cannot compare directly.
  │          A CSP must determine airborne exposure at the use conditions.
  │
  ├─ Input unit = "ppm" AND limit unit = "ppm"?
  │    YES → Direct comparison → COMPLIANT / NON_COMPLIANT
  │
  └─ Unitless concentration AND ppm limit?
       YES → Assume same unit → COMPLIANT / NON_COMPLIANT (best effort, flagged)
```

**Key principle**: Fail-closed defaults apply at every step. A positive evidence of compliance is required to emit `COMPLIANT`. `UNKNOWN` is never interpreted as safe.
