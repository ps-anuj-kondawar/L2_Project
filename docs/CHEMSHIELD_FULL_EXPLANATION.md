# ChemShield AI — Complete Architectural, Code & Conceptual Guide

---

# Part 1: Explaining ChemShield AI to a 10-Year-Old (The Child's Guide)

### Imagine a Magical Laboratory Kitchen
Imagine you are in a super fun, giant science kitchen. You want to mix cool liquids in special jars to make things like paint, medicine, or cleaning potions.

But science liquids can be dangerous:
1. Some liquids make you cough or hurt your lungs if there's too much of it in the air.
2. Some liquids get super hot and can melt plastic cups, spilling everywhere.
3. Some liquids catch on fire if you don't keep them cool.

In a real lab, grown-up scientists have giant rule books written by the government (like OSHA) with thousands of pages of rules. They also have to write a 16-page "Instruction Manual of Warnings" called a **Safety Data Sheet (SDS)** before anyone can use a mixture. Writing this takes days and is super easy to make mistakes on.

### Enter ChemShield AI: The Robot Safety Superhero Team!
Instead of one tired human reading 1,000 pages of rules, **ChemShield AI** is like a team of specialized robot detectives who work together in one second:

```
                          [Detective Boss (Supervisor)]
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
  [The Bookworm]               [The Rule Enforcer]           [The Thermometer Bot]
(Intelligence Agent)            (Chemical Agent)               (Hardware Agent)
   Reads PubChem               Checks OSHA Books             Tests Jars & Heaters
        │                              │                              │
        └──────────────────────────────┼──────────────────────────────┘
                                       ▼
                             [The Master Writer]
                              (SDS Author Agent)
                        Writes the 16-page Manual
                                       │
                                       ▼
                             [The Strict Teacher]
                              (Reflection Agent)
                          "Did you forget anything?"
```

1. **Detective Boss (The Supervisor Agent)**: 
   Takes what you wrote (like *"Mix 10% Benzene in a plastic bottle at 90°C"*), reads it, breaks it down into parts, and gives tasks to the helpers.
2. **The Bookworm (Intelligence Agent)**: 
   Runs to the biggest free science library on earth (PubChem) to check what chemicals are in your mix, what hazard symbols they get (like the flame or skull icon), and what their registration ID is.
3. **The Rule Enforcer (Chemical Agent)**: 
   Opens the strict government rule book (OSHA) and says: *"Wait! Benzene is super toxic. You cannot breathe more than 1 part per million of this, and 10% is dangerous without a fume hood!"*
4. **The Thermometer Bot (Hardware Agent)**: 
   Checks your container. It connects to a special tool server and says: *"Stop! Polyethylene plastic melts at 80°C! You said 90°C, the bottle is going to melt!"*
5. **The Master Writer (SDS Author Agent)**: 
   Collects all the notes from the detectives and writes all 16 chapters of the Safety Data Sheet.
6. **The Strict Teacher (Reflection Agent)**: 
   Takes a red pen and inspects the Master Writer's draft. If the writer forgot to mention emergency phone numbers, or forgot fire extinguisher instructions, the Strict Teacher sends it back with corrections until it's 100% complete.

All of this happens in **less than 2 seconds**, protecting people, saving lives, and making sure labs don't burn down.

---

# Part 2: System Architecture & Data Flow

ChemShield AI is an asynchronous, multi-agent AI safety platform built with Python (FastAPI/Uvicorn), Google Gemini, ChromaDB Vector Search, FastMCP (Model Context Protocol), and SQLite caching.

### Complete Data Flow Diagram
```
User Input (Formulation Text / Web UI / REST Request)
                    │
                    ▼
          src/api/server.py (FastAPI Endpoint)
                    │
                    ▼
        src/agents/supervisor.py (run_supervisor)
                    │
    ┌───────────────┴─────────────────────────┐
    │ 1. Regex & RapidFuzz Pre-Validation     │ (validator.py)
    │ 2. Intent Detection & Entity Extraction │ (LLM / Heuristic)
    │ 3. Check SQLite Semantic Cache          │ (cache.py)
    └───────────────┬─────────────────────────┘
                    ▼
        Concurrent Async Dispatch (asyncio.gather)
    ┌───────────────────────┬────────────────────────┐
    ▼                       ▼                        ▼
IntelligenceAgent      ChemicalAgent           HardwareAgent
(PubChem REST API)     (5-Tier Lookup:         (FastMCP Protocol Tool:
 - Chemical CID         1. Master DB            - Stdio connection
 - CAS Number           2. ChromaDB RAG         - Thermal bounds
 - GHS H/P codes        3. SQLite Cache         - Web search fallback)
 - Pictograms           4. Gemini LLM
                        5. Tavily Web)
    │                       │                        │
    └───────────────────────┼────────────────────────┘
                            ▼
              Verdict Engine Aggregation
      (COMPLIANT / WARNING / NON_COMPLIANT / REVIEW_REQUIRED)
                            │
               Intent == "sds" or "full"?
               ┌────────────┴────────────┐
              No                        Yes
               │                         │
               │                         ▼
               │                SDSAuthorAgent
               │          (16 GHS Sections via Jinja2 & LLM)
               │                         │
               │                         ▼
               │                  ReflectionAgent
               │          (9 Deterministic Guardrail Checks)
               │          ├── Passed? ──> Proceed
               │          └── Failed? ──> Retry with critique
               │                         │
               └────────────┬────────────┘
                            ▼
           Summary & Metrics Calculation
           Two-Tier SQLite Cache Update
           Response Return (JSON / SSE Stream / PDF)
```

---

# Part 3: Exhaustive Directory, File & Function Reference

Every file and every function in `src/` explained with its single responsibility, inputs, outputs, and design rationale.

---

## 3.1. Directory: `src/core/` (Foundational Models, State & Logic)

### File: `src/core/models.py`
Defines strict Pydantic v2 schemas for runtime validation, API serialization, and LLM JSON-mode parsing.

1. **`Intent(str, Enum)`**:
   - Enumeration of user intents: `AUDIT` (compliance check only), `SDS` (safety sheet authoring), `FULL` or `AUDIT_AND_SDS` (both).
2. **`ExtractedChemical(BaseModel)`**:
   - `name`: Chemical name string.
   - `concentration`: Detected concentration string (e.g., `'10%'`, `'50 ppm'`).
3. **`ExtractedHardware(BaseModel)`**:
   - `name`: Name of equipment/container (e.g., `'Borosilicate Beaker'`).
   - `target_temperature_celsius`: Operating temperature in °C.
4. **`ChemicalFlag(BaseModel)`**:
   - Holds compliance finding for a single chemical.
   - Fields: `chemical_name`, `is_compliant` (bool), `status` (`'COMPLIANT'`, `'NON_COMPLIANT'`, `'REVIEW_REQUIRED'`), `detected_concentration`, `regulatory_limit`, `source_citation`, `retrieval_source`.
5. **`HardwareFlag(BaseModel)`**:
   - Holds thermal boundary finding for equipment.
   - Fields: `equipment_name`, `target_temperature_celsius`, `max_safe_temperature_celsius`, `is_compatible`, `status`, `recommendation`.
6. **`PubChemData(BaseModel)`**:
   - Authoritative chemical properties from NCBI PubChem.
   - Fields: `chemical_name`, `cid`, `cas_number`, `molecular_formula`, `molecular_weight`, `iupac_name`, `ghs_hazard_statements` (H-codes), `ghs_precautionary_statements` (P-codes), `ghs_pictograms`, `signal_word`.
7. **`SDSSection(BaseModel)`**:
   - Represents 1 of 16 GHS sections.
   - Fields: `section_number` (1 to 16), `title`, `content` (markdown/text).
8. **`SDSDocument(BaseModel)`**:
   - Complete SDS structure containing all 16 `SDSSection` models, header metadata, GHS pictograms, and generation timestamp.
9. **`ComplianceReport(BaseModel)`**:
   - Final evaluation payload returned to frontend/client. Contains `verdict` (`'COMPLIANT'`, `'NON_COMPLIANT'`, etc.), `chemical_flags`, `hardware_flags`, `sds_document`, `execution_traces`, `metrics`.
10. **`PipelineMetrics(BaseModel)`**:
    - Performance metrics: `total_duration_ms`, `llm_latency_ms`, `rag_context_relevancy`, `cache_hit_rate`, `tokens_used`.

---

### File: `src/core/state.py`
Defines the shared state ("blackboard") passed across all asynchronous agents.

1. **`AgentState`**:
   - Central mutable state object initialized per request.
   - Attributes:
     - `raw_input`: Original user prompt.
     - `intent`: Parsed `Intent`.
     - `chemicals`: List of `ExtractedChemical`.
     - `hardware`: List of `ExtractedHardware`.
     - `chemical_flags`: List of `ChemicalFlag`.
     - `hardware_flags`: List of `HardwareFlag`.
     - `pubchem_data`: Dict mapping chemical name to `PubChemData` dict.
     - `sds_document`: Generated `SDSDocument` (if requested).
     - `reflection_passed`: Boolean guardrail flag.
     - `reflection_notes`: List of error/warning strings from reflection auditor.
     - `execution_traces`: List of step-by-step telemetry events for UI streaming.
     - `metrics`: Dictionary tracking latencies and cache hits.
2. **`AgentState.add_trace(agent, action, observation, duration_ms, status)`**:
   - Records a structured telemetry event into `execution_traces` so the web interface can display real-time timeline steps.

---

### File: `src/core/constants.py`
Authoritative constants, domain dictionaries, and prompt templates.

1. **`MASTER_CHEMICAL_DATABASE`**:
   - Immutable in-memory chemical reference catalog containing CAS numbers, boiling points, OSHA PELs (PPM and % limits), signal words, and GHS hazard statements for primary industrial compounds (Benzene, Toluene, Acetone, Formaldehyde, etc.).
2. **`CAS_TO_NAME`**:
   - Reverse mapping dictionary that maps CAS registry numbers (e.g. `'71-43-2'`) directly to canonical names (`'Benzene'`).
3. **`HARDWARE_LIMITS`**:
   - Maximum continuous operating temperature bounds in Celsius for laboratory containers (e.g., `'borosilicate glass beaker'`: 500°C, `'ptfe beaker'`: 260°C, `'polypropylene bottle'`: 120°C, `'polyethylene bottle'`: 80°C).
4. **`BOILING_POINTS_CELSIUS` & `PHYSICAL_PROPERTIES`**:
   - Known physical constants used for physical plausibility checks and Section 9 SDS generation.
5. **System Prompts & Model Names**:
   - Defines default Gemini model strings (`gemini-3.6-flash`), fallback OpenRouter endpoints, and system prompt templates.

---

### File: `src/core/copilot.py`
Context-aware interactive conversational safety assistant engine.

1. **`_get_single_chemical_context(name: str) -> str`**:
   - Asynchronously searches ChromaDB RAG and falls back to Tavily for a single chemical mentioned in chat to ground the Copilot's answers.
2. **`copilot_chat(query: str, current_audit_context: dict | None, history: list[dict]) -> str`**:
   - Multi-turn chat handler. Extracts chemical names and CAS numbers from the user query using regex and `KNOWN_CHEMICALS`.
   - Checks SQLite conversation cache (`get_conversation_cache`).
   - Injects both active formulation audit results and regulatory RAG context into the LLM system prompt.
   - Calls `llm_chat()` and caches the answer in SQLite.

---

### File: `src/core/logger.py`
1. **`logger`**: Configures Python's `logging` module with standardized formatting (`[timestamp] [level] [agent] message`) for console and file output.

---

### File: `src/core/agent.py`
1. **`BaseAgent(ABC)`**:
   - Abstract Base Class enforcing the design pattern for agents:
     - `abstractmethod async def run(state: AgentState) -> AgentState`
     - `abstractmethod def validate_output(state: AgentState) -> bool`

---

## 3.2. Directory: `src/agents/` (The Multi-Agent Workhorse)

### File: `src/agents/supervisor.py`
The orchestrator managing extraction, agent scheduling, verdict calculation, and retry loops.

1. **`_resolve_cas_to_name(raw_name: str) -> str`**:
   - Uses regex pattern `^\d{2,7}-\d{2}-\d$` to check if a user passed a CAS number instead of a name; resolves it to canonical chemical name.
2. **`_extract_entities_heuristic(text: str) -> tuple[list[ExtractedChemical], list[ExtractedHardware]]`**:
   - Fast deterministic regex parser extracting percentages (`10%`), ppm (`500 ppm`), temperatures (`80°C`), and chemicals without requiring an LLM call.
3. **`_extract_entities_llm(text: str) -> tuple[list[ExtractedChemical], list[ExtractedHardware], Intent]`**:
   - High-accuracy entity and intent extraction using Gemini JSON mode when heuristic extraction is uncertain.
4. **`_calculate_verdict(state: AgentState) -> str`**:
   - Evaluates chemical flags and hardware flags.
   - Returns `'NON_COMPLIANT'` if any limit is exceeded or container is overheating.
   - Returns `'REVIEW_REQUIRED'` if any compound is unknown or units don't align (fail-closed security).
   - Returns `'WARNING'` for minor issues.
   - Returns `'COMPLIANT'` only with positive proof of safety.
5. **`_generate_summary_sentence(state: AgentState) -> str`**:
   - Creates a concise 1-sentence plain-English summary of violations or compliance. Keyed by hash in `summary_cache`.
6. **`run_supervisor(raw_input: str, intent_override: str | None = None) -> ComplianceReport`**:
   - **Primary Pipeline Entrypoint**:
     1. Checks semantic input cache in SQLite.
     2. Extracts entities and normalizes typos via `validator.py`.
     3. Concurrently fires `IntelligenceAgent`, `ChemicalAgent`, and `HardwareAgent` using `asyncio.gather()`.
     4. Aggregates results and calculates compliance verdict.
     5. If intent requires SDS: triggers `SDSAuthorAgent`, runs `ReflectionAgent` to audit; retries up to 2 times if reflection fails.
     6. Stores outputs in SQLite cache and returns final `ComplianceReport`.

---

### File: `src/agents/intelligence_agent.py`
Retrieves authoritative chemical identity and GHS classifications from NCBI PubChem.

1. **`run_intelligence_agent(state: AgentState) -> AgentState`**:
   - Extracts chemical names from `state.chemicals`.
   - Concurrently executes `get_pubchem_data(name)` for every ingredient via `asyncio.gather()`.
   - Populates `state.pubchem_data` with CAS numbers, GHS pictograms, H-codes, P-codes, and molecular properties.
   - Logs trace duration and CIDs found to `state.execution_traces`.

---

### File: `src/agents/chemical_agent.py`
Audits chemical exposure limits using a 5-tier hierarchical search strategy with strict unit tracking.

1. **`_parse_limits(rag_docs: list[str]) -> dict`**:
   - Regex parser extracting PPM exposure limits, percentage ceilings, and source citations from raw regulatory text chunks.
2. **`_search_chemical_safety(chemical_name: str) -> dict | None`**:
   - Tavily live web search fallback when a chemical is not present in local databases or RAG.
3. **`_evaluate_chemical(chem: ExtractedChemical, rag_docs: list[str]) -> ChemicalFlag`**:
   - Evaluates whether the chemical is compliant.
   - Checks `MASTER_CHEMICAL_DATABASE` first (Tier 1).
   - Checks ChromaDB RAG (Tier 2).
   - Checks SQLite cache (Tier 3).
   - Queries Gemini LLM (Tier 4).
   - Queries Tavily web search (Tier 5).
   - **Unit Safety**: Detects if user supplied liquid % while regulatory limit is inhalation PPM. Fails closed with `'REVIEW_REQUIRED'` rather than false compliance.
4. **`run_chemical_agent(state: AgentState) -> AgentState`**:
   - Iterates through all chemicals in `state.chemicals`, evaluates each, and appends `ChemicalFlag` objects to `state.chemical_flags`.

---

### File: `src/agents/hardware_agent.py`
Audits laboratory containers and thermal equipment using the Model Context Protocol (FastMCP).

1. **`_fallback_web_search_hardware(hw_name: str) -> float | None`**:
   - Tavily web search fallback that finds manufacturer temperature limits for exotic or proprietary lab hardware.
2. **`_run_mcp_client(equipment_name: str, target_temp: float) -> dict`**:
   - Spawns a client connection to `src/infrastructure/mcp_server.py` via standard input/output (`stdio_client`) using the official Model Context Protocol (`ClientSession`).
   - Calls the registered tool `check_hardware_compatibility`.
3. **`run_hardware_agent(state: AgentState) -> AgentState`**:
   - Fuzzy-matches container names.
   - Queries MCP server tool. If unknown, invokes web search fallback.
   - Compares target temperature to maximum safe temperature.
   - Emits `HardwareFlag` with status `'COMPLIANT'` or `'NON_COMPLIANT'`.

---

### File: `src/agents/sds_author_agent.py`
Synthesizes all gathered intelligence into an official 16-section GHS Safety Data Sheet.

1. **`_clean_section_title(sec_num: int, raw_title: str) -> str`**:
   - Strips redundant section numbering prefixes (e.g. converting `"SECTION 1: Identification"` to `"Identification"`).
2. **`_build_section_prompt(sec_num: int, sec_title: str, state: AgentState) -> str`**:
   - Constructs grounded prompt for generating an individual GHS section, injecting PubChem data, chemical flags, and regional regulatory requirements.
3. **`run_sds_author_agent(state: AgentState, critique_notes: list[str] | None = None) -> AgentState`**:
   - Assembles all 16 GHS sections:
     - Section 1: Identification & Emergency Contacts
     - Section 2: Hazard(s) Identification (GHS pictograms, Signal Word)
     - Section 3: Composition / Information on Ingredients (CAS numbers)
     - Section 4: First-Aid Measures
     - Section 5: Fire-Fighting Measures
     - Section 6: Accidental Release Measures
     - Section 7: Handling and Storage
     - Section 8: Exposure Controls / Personal Protection (OSHA PELs, PPE)
     - Section 9: Physical and Chemical Properties (Boiling/Flash points)
     - Section 10: Stability and Reactivity
     - Section 11: Toxicological Information (IARC/NTP Carcinogens)
     - Section 12: Ecological Information
     - Section 13: Disposal Considerations (RCRA waste codes)
     - Section 14: Transport Information (UN numbers, DOT/IMDG)
     - Section 15: Regulatory Information (TSCA, SARA Title III, REACH)
     - Section 16: Other Information (NFPA 704 ratings, revision date)
   - Incorporates reflection critique notes if running as a self-correction retry.
   - Produces structured `SDSDocument` attached to `state.sds_document`.

---

### File: `src/agents/reflection_agent.py`
Deterministic safety guardrail agent auditing generated SDS documents before delivery.

1. **`run_reflection_agent(state: AgentState) -> AgentState`**:
   - Audits `state.sds_document` against 9 mandatory safety criteria:
     1. **Section Count**: Verifies all 16 sections exist and are non-empty.
     2. **CAS Hallucination Check**: Validates CAS numbers in Section 3 against PubChem.
     3. **Exposure Limit Leakage**: Ensures OSHA PEL limits are in Section 8, not Section 3.
     4. **PPE Completeness**: Checks that Section 8 specifies eye, skin, and respiratory protection.
     5. **UN Transport Classification**: Checks Section 14 for valid UN numbers or "Not Regulated".
     6. **Statutory Regulatory References**: Confirms Section 15 cites OSHA, TSCA, or REACH.
     7. **Emergency Contacts**: Verifies Section 1 includes emergency contact details.
     8. **Physical Properties**: Confirms Section 9 lists boiling point or physical state.
     9. **Carcinogen Disclosure**: Checks if known carcinogens (Benzene, Formaldehyde) have explicit IARC/NTP citations in Section 11.
   - If any check fails: sets `state.reflection_passed = False` and populates `state.reflection_notes` for supervisor retry.

---

## 3.3. Directory: `src/infrastructure/` (APIs, Caching, Protocols & Output)

### File: `src/infrastructure/cache.py`
Thread-safe, multi-tier SQLite caching system enabling zero-latency repeats and zero unnecessary API billing.

1. **`_init_db()`**:
   - Executed once on import. Enables SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and creates 5 tables: `osha_cache`, `summary_cache`, `input_cache`, `conversation_cache`, `pubchem_cache`.
2. **`_get_connection() -> sqlite3.Connection`**:
   - Returns a thread-local SQLite connection (`_local.conn`) to eliminate multi-threaded lock contention.
3. **Cache Getters & Setters**:
   - `get_osha_limits(chem_name: str) -> dict | None` & `set_osha_limits(...)`
   - `get_semantic_cache(input_text: str, intent: str) -> dict | None` & `set_semantic_cache(...)`
   - `get_summary_cache(violations_fingerprint: str) -> str | None` & `set_summary_cache(...)`
   - `get_conversation_cache(query: str) -> str | None` & `set_conversation_cache(...)`
   - `get_pubchem_cache(chem_name: str) -> dict | None` & `set_pubchem_cache(...)`

---

### File: `src/infrastructure/mcp_server.py`
Implements the Model Context Protocol (FastMCP) server over `stdio` transport.

1. **`_resolve_equipment_key(equipment_name: str) -> str | None`**:
   - Normalizes input equipment name to match canonical keys in `HARDWARE_LIMITS`.
2. **`check_hardware_compatibility(equipment_name: str, target_temperature_celsius: float) -> dict`**:
   - MCP tool function registered via `@mcp.tool()`.
   - Checks if temperature exceeds equipment limits.
   - Returns compatibility boolean, rated limit, delta temperature, and safety verdict.

---

### File: `src/infrastructure/pubchem_client.py`
Asynchronous REST client for NCBI PubChem PUG REST API.

1. **`_get_semaphore() -> asyncio.Semaphore`**:
   - Concurrency limiter (max 5 simultaneous requests) preventing HTTP 429 throttling from NCBI.
2. **`_fetch_json(url: str, timeout: float = 10.0) -> dict | None`**:
   - Asynchronous HTTP GET helper using `httpx.AsyncClient`.
3. **`get_pubchem_data(chemical_name: str) -> PubChemData`**:
   - Resolves chemical name to PubChem Compound ID (CID).
   - Fetches CAS numbers, molecular weight, formula, and IUPAC name.
   - Parses GHS classifications: extracts H-codes, P-codes, signal words (`DANGER`/`WARNING`), and pictogram names.
   - Stores results in SQLite `pubchem_cache`.

---

### File: `src/infrastructure/llm_client.py`
High-reliability LLM interface supporting Google Gemini and OpenRouter.

1. **`_call_gemini(prompt: str, system_instruction: str | None, json_mode: bool) -> str`**:
   - Executes completion via `google-genai` SDK using `gemini-3.6-flash`.
2. **`_call_openrouter(prompt: str, system_instruction: str | None, json_mode: bool) -> str`**:
   - Backup provider called automatically if Gemini quota is exceeded.
3. **`chat(prompt: str, system_instruction: str | None = None, json_mode: bool = False) -> str`**:
   - Unified interface with automatic failover and retry logic.

---

### File: `src/infrastructure/rag.py`
OSHA regulatory vector retrieval using ChromaDB.

1. **`_get_collection()`**:
   - Lazy-initializes ChromaDB `PersistentClient` targeting `./chroma_db`.
2. **`query_regulations(chemical_name: str, region: str = "US") -> list[str]`**:
   - Queries vector collection for embedded OSHA 1910 standards and NIOSH Pocket Guide chunks matching the chemical.

---

### File: `src/infrastructure/pdf_generator.py`
Publication-grade PDF rendering engine conforming to OSHA HazCom 2012.

1. **`NumberedCanvas(canvas.Canvas)`**:
   - Two-pass ReportLab canvas calculating dynamic "Page X of Y" footers.
2. **`generate_sds_pdf(sds: SDSDocument) -> bytes`**:
   - Formats all 16 GHS sections, hazard warnings, GHS pictograms, and revision headers into ReportLab Platypus elements.
   - Generates and returns raw PDF byte stream for browser download or printing.

---

## 3.4. Directory: `src/utils/` (Rules, Sanity Checks & Validators)

### File: `src/utils/ghs_rules.py`
Pure-Python GHS Revision 9 classification and regulatory rule engine.

1. **`GHS_PICTOGRAM_FILES`**: Mapping of GHS codes (`GHS01`–`GHS09`) to SVG pictogram filenames.
2. **`DANGER_H_CODES`**: Set of high-severity hazard codes (e.g., `H350` Carcinogenicity, `H310` Fatal in contact with skin) that mandate the `'DANGER'` signal word.
3. **`UN_TRANSPORT_DATABASE`**: Authoritative UN numbers, shipping names, and packaging groups for transport compliance.
4. **`determine_overall_signal_word(h_codes: list[str]) -> str`**:
   - Returns `'DANGER'` if any code is in `DANGER_H_CODES`; otherwise `'WARNING'`.
5. **`get_mixture_un_transport_info(chemicals: list[str]) -> dict`**:
   - Determines dominant UN transport classification for mixtures.
6. **`get_carcinogen_info(chemical_name: str) -> dict | None`**:
   - Checks IARC, NTP, and California Proposition 65 carcinogen lists.
7. **`load_pictogram_svg(pictogram_code: str) -> str`**:
   - Loads SVG vector graphic markup for rendering GHS diamonds.

---

### File: `src/utils/validator.py`
Input sanitization, typo correction, and physical plausibility validation.

1. **`fuzzy_match_chemical(name: str) -> tuple[str, float]`**:
   - Uses RapidFuzz `WRatio` against `KNOWN_CHEMICALS` (e.g., corrects `'benzen'` to `'Benzene'`).
2. **`validate_and_correct_chemicals(chemicals: list[tuple[str, str]]) -> tuple[list, list]`**:
   - Corrects misspelled chemicals in extracted lists while logging corrections made.
3. **`fuzzy_match_hardware(name: str) -> tuple[str, float]`**:
   - Fuzzy-matches container names to canonical hardware entries.
4. **`validate_physical_boundaries(state: AgentState) -> list[str]`**:
   - Checks for physical impossibilities (e.g., operating temperature above 1500°C or chemical concentrations > 100%).

---

## 3.5. Directory: `src/api/` & `src/ui/` (Web Application & Server)

### File: `src/api/server.py`
FastAPI web server exposing REST endpoints, Server-Sent Events (SSE), and static file mounts.

1. **`add_no_cache_header(request, call_next)`**:
   - Middleware ensuring static assets never cache during evaluation or development.
2. **`GET /api/stream`**:
   - Server-Sent Events (SSE) endpoint providing live streaming telemetry of multi-agent execution steps directly to frontend UI.
3. **`POST /api/evaluate`**:
   - Accepts laboratory formulation queries and triggers `run_supervisor()`.
4. **`POST /api/copilot/chat`**:
   - Handles multi-turn conversational questions with the RAG-grounded Safety Copilot.
5. **`POST /api/export-pdf`**:
   - Converts an `SDSDocument` to downloadable PDF bytes via `generate_sds_pdf()`.
6. **`GET /api/scenarios`**:
   - Returns curated laboratory formulation test scenarios for one-click testing in the web dashboard.

---

### File: `src/ui/app.py`
1. **`create_app() -> FastAPI`**:
   - Factory function mounting static directories (`static/`, `templates/`) and serving `index.html`.

---

## 3.6. Directory: `src/scripts/` (Database Ingestion & Benchmarking)

### File: `src/scripts/ingest.py`
1. **`ingest_regulations()`**:
   - Reads regulatory source texts from `data/osha_standards.json`.
   - Chunks text into semantic regulatory paragraphs.
   - Embeds and indexes chunks into ChromaDB persistent storage collection.

### File: `src/scripts/run_benchmark.py`
1. **`evaluate_scenario(scenario: dict) -> dict`**:
   - Runs a single golden scenario from `benchmark_dataset.jsonl` through `run_supervisor()`.
2. **`run_benchmark()`**:
   - Computes precision, recall, accuracy, and latency percentiles across all test scenarios, writing results to `benchmark_results.json`.

---

# Part 4: Key Interview Questions & Defenses

### Q1: Why use a Multi-Agent architecture instead of a single prompt to GPT-4 or Claude?
**Defense:** A single LLM prompt suffers from **hallucination of regulatory limits**, **lack of determinism**, and **context drift**. 
- In ChemShield AI, **chemical identity** is decoupled to PubChem REST API (ground truth).
- **Physical hardware limits** are decoupled to an isolated Model Context Protocol (FastMCP) server.
- **Regulatory limits** are grounded via ChromaDB vector RAG over actual OSHA standards.
- **The Reflection Agent** provides an automated programmatic verification gate.
Dividing duties into specialized agents guarantees auditability and deterministic safety.

### Q2: What is the "Fail-Closed" philosophy in ChemShield AI?
**Defense:** In laboratory safety, **unknown does not equal safe**. If an unknown chemical or unverified concentration is entered, ChemShield AI returns `REVIEW_REQUIRED` (non-compliant by default) rather than assuming safety. Furthermore, comparing liquid % to airborne inhalation PPM is scientifically invalid; the system recognizes this mismatch and flags it for human safety review.

### Q3: How does ChemShield AI prevent high API billing and latency?
**Defense:** Through a 5-tier architecture:
1. Master in-memory database handles known substances in **0 ms**.
2. Two-tier persistent SQLite cache with Write-Ahead Logging caches PubChem queries, OSHA embeddings, and LLM completions.
3. Redundant queries take **< 5 ms** with **$0 API cost**.

---
*Document complete. Sourced directly from active codebase in `c:\L2_Project`.*
