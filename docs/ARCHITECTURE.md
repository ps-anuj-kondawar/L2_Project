# ChemShield AI - Technical Architecture & Detailed Workflow Documentation

**Version**: 2.5.0 (Enterprise Production Release)  
**System**: Multi-Agent OSHA Compliance Auditing & Multi-Region GHS SDS Platform  
**Target Environment**: High-Performance Asynchronous Python (FastAPI / Uvicorn)

---

## 1. Executive System Architecture

ChemShield AI is an enterprise multi-agent safety intelligence platform designed to evaluate chemical formulations against OSHA HazCom safety regulations, PubChem toxicological registries, and container material thermal limits. 

The system decouples compliance auditing from document synthesis using an **Intent-Driven Multi-Agent Architecture**, enabling sub-second safety evaluations while supporting full 16-section GHS Safety Data Sheet (SDS) generation on demand across multiple international regulatory jurisdictions and languages.

```
                                +---------------------------------------------+
                                |               User / Client UI              |
                                +---------------------------------------------+
                                                       |
                                           HTTP REST / SSE Stream
                                                       |
                                                       v
                                +---------------------------------------------+
                                |             FastAPI Web Server              |
                                +---------------------------------------------+
                                                       |
                                                       v
                                +---------------------------------------------+
                                |         Supervisor Agent Orchestrator       |
                                +---------------------------------------------+
                                                       |
                         +-----------------------------+-----------------------------+
                         |                             |                             |
                         v                             v                             v
           +---------------------------+ +---------------------------+ +---------------------------+
           |    Intelligence Agent     | |      Chemical Agent       | |      Hardware Agent       |
           |  (PubChem PUG REST API)   | |  (OSHA RAG + Tavily Web)  | |   (FastMCP Tool Protocol) |
           +---------------------------+ +---------------------------+ +---------------------------+
                         |                             |                             |
                         +-----------------------------+-----------------------------+
                                                       |
                                                       v
                                +---------------------------------------------+
                                |       Safety Verdict & Summary Engine       |
                                +---------------------------------------------+
                                                       |
                                       [ intent == "audit_and_sds" / "sds" ]
                                                       |
                                                       v
                                +---------------------------------------------+
                                |      SDS Authoring & Reflection Loop        |
                                |     (16-Section Multi-Region Generator)     |
                                +---------------------------------------------+
```

---

## 2. In-Depth Execution Workflow

The pipeline operates through a deterministic 7-phase execution lifecycle. Each phase is monitored and tracked in real time via Server-Sent Events (SSE).

### Phase 1: Request Ingress & Intent Routing
- **Entry Point**: The request lands at `/api/v1/stream` or `/api/v1/audit` in `src/api/server.py`.
- **Parameters**: Inputs include `input_text` (formulation string), `intent` (`audit`, `sds`, `audit_and_sds`), `region` (`US`, `EU`, `JP`, `CA`, `GB`), and `language` (`en`, `es`, `fr`, `de`, `ja`).
- **Cache Check (Phase 0)**: The Supervisor queries `src/infrastructure/cache.py` using an SHA-256 hash of the normalized formulation text. On a cache hit, the system bypasses all downstream agent execution and returns the cached result in ~0.005 seconds.

### Phase 2: Entity Extraction & Normalization
- **Supervisor Agent** (`src/agents/supervisor.py`) invokes the LLM (`src/infrastructure/llm_client.py`) with JSON output constraints to parse raw unstructured formulation text into structured data models:
  - **Chemical Entities**: Extracted chemical names and detected concentrations (e.g., `94% Water`, `6% Benzene`, `500 ppm Acetone`).
  - **Hardware Entities**: Extracted container or equipment names and target operating temperatures (e.g., `borosilicate glass beaker at 50C`, `polypropylene container at 90C`).
- **Fuzzy Auto-Correction**: Misspelled chemical names are cross-referenced against authoritative dictionaries (`src/utils/validator.py`) to prevent missing critical safety matches.

### Phase 3: Parallel Agent Execution
Once entities are extracted, the Supervisor dispatches three specialized agents asynchronously using `asyncio.gather()`:

1. **Intelligence Agent** (`src/infrastructure/pubchem_client.py`):
   - Queries the PubChem PUG REST API to fetch authoritative compound CIDs, CAS numbers, molecular weight, GHS pictogram codes (`GHS02`, `GHS08`), signal words (`DANGER`, `WARNING`), and hazard statements.
   - Saves responses to local SQLite `pubchem_cache` with a 7-day TTL to eliminate redundant external network calls.

2. **Chemical Compliance Agent** (`src/agents/chemical_agent.py`):
   - Queries a ChromaDB vector database (`src/infrastructure/rag.py`) containing indexed OSHA Permissible Exposure Limits (PELs).
   - If vector relevancy falls below standard thresholds or a chemical is unindexed, it executes a fallback query using the Tavily Web Search API to ground the safety limit against live OSHA/CDC regulatory sources.
   - Evaluates chemical concentrations against OSHA volume percentage cut-offs (e.g., Benzene 0.1% limit) and airborne PPM TWA exposure limits.

3. **Hardware Compliance Agent** (`src/agents/hardware_agent.py`):
   - **Fast-Path Check**: Performs an in-memory dictionary lookup against known container limits (`HARDWARE_LIMITS` in `src/core/constants.py`).
   - **Slow-Path FastMCP Protocol**: For non-standard equipment, opens an isolated subprocess (`src/infrastructure/mcp_server.py`) using the standard Model Context Protocol (`mcp.client.stdio`) to evaluate container thermal safety.

### Phase 4: Deterministic Safety Verdict & Summary Synthesis
- **Verdict Calculation**: The Supervisor evaluates flags from all agents:
  - **`APPROVED`**: All chemical concentrations are within OSHA regulatory limits and equipment operating temperatures are below maximum safe thresholds.
  - **`REJECTED`**: Any chemical concentration exceeds OSHA PELs or container operating temperature exceeds hardware thermal safety limits.
  - **`PARTIAL`**: Secondary physical hazards detected (e.g., target operating temperature exceeds liquid boiling point causing pressure buildup).
- **Summary Generation**: The LLM synthesizes a concise, authoritative one-sentence safety summary citing exact violations and limits.

### Phase 5: GHS SDS Authoring (Multi-Region & Multi-Language)
If the user intent includes SDS generation (`audit_and_sds` or `sds`), the **SDS Authoring Agent** (`src/agents/sds_author_agent.py`) synthesizes formulation facts into a 16-section GHS Safety Data Sheet:
- **Regional Regulatory Adaptation**:
  - **US**: US OSHA HazCom 2012 / GHS Rev.9 (includes OSHA PELs, SARA 313, California Proposition 65).
  - **EU**: EU REACH (EC 1907/2006) & CLP (EC 1272/2008) (includes EU OELs, REACH Annex II).
  - **JP**: Japan JIS Z 7253:2019 & Industrial Safety and Health Law (ISHL).
  - **CA**: Canada WHMIS 2015 / Hazardous Products Regulations (HPR).
  - **GB**: UK GB-CLP & Health and Safety Executive (HSE) standards.
- **Language Localization**: All 16 section titles, hazard descriptions, PPE guidelines, and regulatory disclosures are written entirely in the selected language (`English`, `Spanish`, `French`, `German`, `Japanese`).

### Phase 6: Automated Quality Assurance via Reflection Loop
- **Reflection Agent**: Evaluates the generated 16-section SDS document structure and content against GHS completeness guidelines.
- **Auto-Correction**: If required sections or hazard disclosures are incomplete, the Reflection Agent supplies feedback to the SDS Authoring Agent to re-generate sections (up to 2 iterations).

### Phase 7: Real-Time SSE Telemetry & HTML Rendering
- **Server-Sent Events (SSE)**: Execution logs, progress steps, agent telemetry, and JSON payloads are streamed in real time to the browser interface (`static/app.js`).
- **Jinja2 HTML Rendering**: The final `SDSDocument` is rendered into a clean, printable HTML document using `templates/sds_template.html`.

---

## 3. Data Models & State Lifecycle

Pipeline execution state is encapsulated within the `AgentState` dataclass (`src/core/state.py`):

```python
@dataclass
class AgentState:
    user_input: str
    run_id: str
    intent: str
    region: str
    language: str
    chemicals: list[ExtractedChemical]
    hardware: list[ExtractedHardware]
    pubchem_data: dict[str, Any]
    chemical_flags: list[ChemicalFlag]
    hardware_flags: list[HardwareFlag]
    sds_document: SDSDocument | None
    sds_html: str | None
    reflection_notes: list[str]
    reflection_passed: bool
    trace: list[TraceStep]
    overall_status: str
```

---

## 4. Token & Cost Optimization Architecture

ChemShield AI incorporates five key layers of token and operational cost reduction:

1. **Two-Tier SQLite Caching**:
   - `input_cache`: Serializes full `AgentRunResult` keyed by input hash. Bypasses LLM entirely on repeated requests (~0 tokens, ~0.005s latency).
   - `pubchem_cache`: Caches raw PubChem REST responses locally with a 7-day TTL.
   - `summary_cache`: Reuses safety summaries for identical violation sets.
2. **In-Memory Hardware Fast-Path**: Eliminates LLM and MCP tool calls for common equipment (e.g. borosilicate glass, polypropylene).
3. **Task-Specific Agentic Prompts**: Splits monolithic tasks into minimal prompt calls (Extraction, Chemical Audit, SDS Generation), avoiding large prompt context bloat.
4. **Bounded RAG Vector Retrieval**: Retrieves strictly `RAG_TOP_K = 5` chunks from ChromaDB, preventing context window stuffing.
5. **Provider & Model Routing**: Routes lightweight extraction tasks to fast/cheap models (Gemini Flash or OpenRouter free tier) while reserving larger models strictly for SDS authoring.

---

## 5. Security & Isolation Architecture

- **No Hardcoded Secrets**: All API credentials (`GEMINI_API_KEY`, `TAVILY_API_KEY`, `OPENROUTER_API_KEY`) are managed via environment variables.
- **FastMCP Process Sandboxing**: Hardware tool execution runs in an isolated Python subprocess via stdio transport, preventing arbitrary code execution.
- **Thread Safety**: SQLite connection pooling utilizes `threading.local()` and Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) to handle concurrent FastAPI requests safely.
