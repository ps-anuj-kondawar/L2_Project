# ChemShield AI — Architecture & Technical Specifications

**Version:** 2.0.0 (Production)  
**System:** Multi-Agent OSHA Compliance Auditing & GHS SDS Platform  
**Target Environment:** Local & Enterprise Cloud Deployment  

---

## 1. System Overview & Executive Architecture

ChemShield AI is an intelligent, multi-agent laboratory safety platform designed to evaluate raw chemical formulation notes against environmental safety regulations and hardware operating thresholds.

The platform separates compliance auditing from document synthesis using an **Intent-Driven Architecture**, allowing users to perform rapid compliance safety checks in ~1 second, while providing full 16-section GHS Safety Data Sheet (SDS) generation on demand.

```
                                +---------------------------------------------+
                                |               User / Client UI              |
                                +---------------------------------------------+
                                                       |
                                           REST API / SSE Stream
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
                                       [ intent == "sds" / "full" ]
                                                       |
                                                       v
                                +---------------------------------------------+
                                |      SDS Authoring & Reflection Loop        |
                                |     (GHS 16-Section HTML Generator)         |
                                +---------------------------------------------+
```

---

## 2. Intent-Driven Pipeline Execution

The system supports granular intent scoping to eliminate unnecessary LLM processing latency:

1. **`intent="audit"` (Default Compliance Mode)**:
   - Performs Entity Extraction (chemical names, concentrations, hardware items, target temperatures).
   - Concurrently executes `IntelligenceAgent`, `ChemicalAgent`, and `HardwareAgent`.
   - Computes overall safety status (`APPROVED`, `PARTIAL`, `REJECTED`) and generates a 1-sentence safety summary.
   - **Runtime**: ~1.0–1.5 seconds (0.007s on cache hit).

2. **`intent="sds"` (On-Demand SDS Authoring Mode)**:
   - Detects if compliance audit data is already present in the SQLite semantic cache.
   - **Direct Generation**: If audited state exists, skips entity extraction, RAG search, Tavily lookups, and MCP calls, proceeding directly to 16-section GHS SDS authoring.
   - **Runtime**: ~1.5–2.5 seconds.

3. **`intent="full"` (Full Execution Mode)**:
   - Runs full compliance auditing, GHS SDS synthesis, and automated Reflection review in a single pass.

---

## 3. Specialized Multi-Agent Roles

### 3.1 Supervisor Agent (`src/agents/supervisor.py`)
- **Role**: Orchestrates pipeline lifecycle, parses user intent, manages `AgentState`, handles thread-safe logging, and writes to the SQLite cache.
- **Key Logic**: Executes Step 0 (Cache Check), Step 1 (Extraction & Fuzzy Matching), Step 2 (Parallel Agent Dispatch), Step 3 (Safety Verdict Computation), and Step 5 (SDS Authoring & Reflection).

### 3.2 Intelligence Agent (`src/infrastructure/pubchem_client.py` & `src/agents/intelligence_agent.py`)
- **Role**: Retrieves official GHS hazard classifications directly from the PubChem PUG REST API.
- **Data Extracted**: Compound CIDs, CAS registration numbers, GHS pictogram codes (e.g. `GHS02`, `GHS07`), signal words (`DANGER`, `WARNING`), and hazard statements.

### 3.3 Chemical Agent (`src/agents/chemical_agent.py` & `src/infrastructure/rag.py`)
- **Role**: Evaluates chemical concentrations against OSHA Permissible Exposure Limits (PELs).
- **RAG Subsystem**: Queries a persistent ChromaDB vector database indexed with OSHA regulatory standards.
- **Web Search Fallback**: If ChromaDB vector relevancy falls below threshold, dispatches Tavily Web Search API to ground exposure limits against live regulatory documentation.

### 3.4 Hardware Agent (`src/agents/hardware_agent.py` & `src/infrastructure/mcp_server.py`)
- **Role**: Audits equipment thermal limits to prevent explosive glass failures or plastic melting.
- **Fast-Path Lookup**: Uses an in-memory hardware dictionary for instantaneous validation.
- **FastMCP Protocol**: Connects via Model Context Protocol (MCP) tool call when non-standard equipment is encountered.

### 3.5 SDS Authoring Agent (`src/agents/sds_author_agent.py`)
- **Role**: Synthesizes formulation data, PubChem records, and compliance flags into a 16-section OSHA HazCom 2012 / GHS Rev.9 document.
- **Rendering**: Generates structured JSON sections via Gemini LLM and renders full HTML output using Jinja2 templates (`templates/sds_template.html`).

### 3.6 Reflection Agent (`src/agents/reflection_agent.py`)
- **Role**: Automated Quality Assurance auditor.
- **Validation**: Verifies GHS document structural completeness, signal word consistency, and safety statement alignment. Triggers auto-correction loop if validation fails (max 2 retries).

---

## 4. Caching & Performance Architecture

The platform uses a two-tier SQLite caching system stored in `cache.db`:

1. **`input_cache`**: Stores serialized `AgentRunResult` objects keyed by SHA-256 hash of formulation inputs.
2. **`summary_cache`**: Caches LLM-generated safety summaries keyed by unique violation signature hashes.
3. **`pubchem_cache`**: Caches PubChem PUG REST API responses to avoid external network calls on repeated chemical names.

**Thread Safety**: Uses `threading.local()` connection pooling with SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) for concurrent execution safety under multi-threaded FastAPI request loads.

---

## 5. Frontend & Telemetry Architecture

- **Right-Hand Sidebar Layout**: Main workspace on the left, sticky real-time telemetry sidebar on the right.
- **Pulsing Live Status Dot**: Visual indicator displaying pipeline execution state (`● LIVE`).
- **4-Stage Progress Tracker**:
  - `Step 1: Entity Extraction`
  - `Step 2: Multi-Agent Audit`
  - `Step 3: Safety Verdict`
  - `Step 4: GHS SDS Authoring`
- **Real-Time Stream Terminal**: Displays Server-Sent Events (SSE) streamed live from `/api/v1/stream`.
- **Standalone SDS PDF Worker Modal**: Automatic popup modal containing the rendered GHS SDS document with full-color print capabilities (`print-color-adjust: exact`).
- **Safety Copilot**: Interactive chatbot grounded in active formulation context.
