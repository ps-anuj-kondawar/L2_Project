# Software Requirements Specification (SRS)

**Project Name:** ChemShield AI - Chemical Safety & Multi-Region GHS SDS Platform  
**Specification Version:** 3.1.0 (Revised — Regulatory Remediation Release)  
**Document Status:** Approved & Implemented  

---

## 1. Executive Summary

ChemShield AI is an enterprise-grade, multi-agent chemical safety compliance auditor and GHS Safety Data Sheet (SDS) authoring platform. The system ingests raw laboratory formulation notes, extracts chemical ingredients and laboratory hardware configurations, audits them against regulatory safety standards (OSHA PELs), and generates comprehensive 16-section GHS Safety Data Sheets customizable by international regulatory jurisdiction and language.

This project was specifically architected to fulfill and exceed the capstone deliverables for the **LevelUp: AI Engineering Launchpad** (Level 1 Foundation & Level 2 Practitioner tracks).

---

## 2. Course Alignment: L1 & L2 Capstone Deliverables

This section explicitly maps the platform's architectural implementations to the LevelUp course rubrics, ensuring mentors have a clear understanding of the applied learning outcomes.

### 2.1 Level 1 (Foundation) Alignment
The L1 track focuses on LLM fundamentals, effective prompting, and building a minimal RAG assistant.
*   **Minimal RAG Assistant:** ChemShield AI implements a grounded retrieval pipeline. It chunks and embeds OSHA regulatory standards into a local **ChromaDB vector database**. When an audit is run, it performs a similarity search to retrieve specific Permissible Exposure Limits (PELs).
*   **Prompt Engineering & Context Design:** The system utilizes strict, persona-driven system prompts with heavily restricted context windows (`RAG_TOP_K = 5`) to prevent context stuffing and hallucination. 
*   **Vector Search & Embeddings:** Implements `sentence-transformers` for embedding regulatory texts and user queries.
*   **Fallback Logic:** If the vector database yields low-confidence results, the system gracefully falls back to web retrieval via the Tavily API.

### 2.2 Level 2 (Practitioner) Alignment
The L2 track focuses on advanced agentic patterns, Model Context Protocol (MCP), reflection, and observability.
*   **Multi-Agent Architecture:** Moved beyond single monolithic prompts to an Intent-Driven Multi-Agent Pipeline. The architecture consists of a Supervisor Orchestrator, an Intelligence Agent (PubChem REST API), a Chemical Agent (RAG/Tavily), a Hardware Agent (MCP), an SDS Authoring Agent, and a Reflection Agent.
*   **Model Context Protocol (MCP):** To validate hardware safety (e.g., container thermal limits), the system spins up an isolated `FastMCP` sub-process. The `HardwareAgent` connects to this MCP server over `stdio` to execute tool calls safely, demonstrating secure tool-use patterns.
*   **Reflection & Planning:** The `ReflectionAgent` evaluates the generated 16-section SDS document against GHS completeness guidelines. It acts as a critic and enforces a stop condition (maximum of 2 reflection iterations) to correct formatting errors or missing hazard statements before presenting the final document.
*   **Automated Evals & Observability (SWE-Bench Style):** 
    *   *Offline Evals:* A `run_benchmark.py` script uses the `ragas` framework and an LLM-as-a-judge to mathematically evaluate the pipeline's Context Precision, Answer Relevancy, and Faithfulness against a ground-truth JSONL dataset.
    *   *Live Telemetry:* The UI features real-time Server-Sent Events (SSE) streaming and live metric scorecards (Latency, RAG Relevancy, MCP Success Rate, LLM Instruction Following).

---

## 3. Detailed System Architecture

The system decouples compliance auditing from document synthesis using an **Intent-Driven Multi-Agent Architecture**.

1.  **Supervisor Orchestrator (`src/agents/supervisor.py`)**: Routes the user's intent (`audit` vs `full sds`) and coordinates parallel execution of sub-agents.
2.  **Entity Extraction**: Parses raw user input to identify chemical components, concentrations, and hardware.
3.  **Chemical Agent**: Executes the RAG pipeline against ChromaDB to verify exposure limits.
4.  **Hardware Agent**: Connects to the FastMCP server to validate hardware thermal limits.
5.  **Intelligence Agent**: Queries PubChem for standard GHS pictograms and hazard codes.
6.  **SDS Authoring Agent**: Synthesizes the aggregated telemetry into a localized 16-section SDS.
7.  **Reflection Agent**: Audits the generated SDS and self-corrects prior to finalizing.

---

## 4. Functional Requirements

### FR-1: Formulation Input & Entity Extraction
*   **FR-1.1**: The system shall accept unstructured plain text inputs describing laboratory formulations (chemicals, volumes/masses, containers, and operating temperatures).
*   **FR-1.2**: The extraction engine shall isolate entities and utilize `rapidfuzz` to automatically correct spelling variations in chemical names (e.g., `benzen` to `Benzene`) and hardware types.
*   **FR-1.3**: The system shall accept CAS Registry Numbers (e.g., `71-43-2`) as chemical identifiers. Recognized CAS numbers shall be resolved to chemical names using the `CAS_TO_NAME` mapping derived from `MASTER_CHEMICAL_DATABASE` before any downstream processing.
*   **FR-1.4**: The copilot shall detect CAS numbers mentioned in free-text chat messages and resolve them to chemical names for regulatory context lookup.

### FR-2: Regulatory Data Retrieval — 5-Tier Strategy
*   **FR-2.1**: The `ChemicalAgent` shall evaluate all chemicals against a prioritized 5-tier retrieval strategy (in order): `MASTER_CHEMICAL_DATABASE` (hardcoded authoritative limits) → ChromaDB RAG → SQLite semantic cache → Gemini API direct knowledge lookup → Tavily live web search.
*   **FR-2.2**: The `MASTER_CHEMICAL_DATABASE` in `src/core/constants.py` shall be treated as the single authoritative source for regulatory limits and shall always take precedence over the SQLite cache. Cache entries with `ppm=None` shall be treated as cache misses (not as evidence of no limit existing).
*   **FR-2.3**: The retrieval pipeline must restrict retrieved RAG context to the top 5 chunks.
*   **FR-2.4**: The Gemini API chemical lookup shall be queried before Tavily web search for common OSHA-regulated chemicals. The prompt shall instruct the model to return `null` rather than fabricate uncertain values.
*   **FR-2.5**: Unit semantics must be preserved: `ppm` (airborne exposure) and `%` (liquid formulation) are different physical quantities and must never be directly compared. When units are incompatible, the system shall return `REVIEW_REQUIRED`, not `NON_COMPLIANT`.

### FR-3: MCP Hardware Tool Integration
*   **FR-3.1**: The system shall initialize an independent Model Context Protocol (MCP) server.
*   **FR-3.2**: The `HardwareAgent` shall establish a connection to the MCP server and pass the extracted hardware limits for validation, returning a definitive boolean flag for thermal safety.
*   **FR-3.3**: The MCP server shall perform normalized key matching (lowercase + substring match) to handle equipment naming variations (e.g., 'Borosilicate Glass Beaker' matches 'borosilicate glass beaker').

### FR-4: Intent-Driven Pipeline Execution
*   **FR-4.1 (Fast Path)**: If the user requests an `audit`, the pipeline shall bypass SDS document generation, calculate the safety verdict (`APPROVED`, `PARTIAL`, `REJECTED`), and return results in ~1-2 seconds.
*   **FR-4.2 (Full Path)**: If the user requests an `sds`, the pipeline shall trigger the `SDSAuthorAgent` to generate a 16-section document localized by region (US, EU, JP) and language.

### FR-5: User Interface & Real-Time Telemetry
*   **FR-5.1**: The frontend shall be a FastAPI-served Single Page Application utilizing raw HTML/JS/CSS (glassmorphism design).
*   **FR-5.2**: The UI shall maintain a live connection to the backend via Server-Sent Events (SSE) to stream the execution trace logs dynamically.
*   **FR-5.3**: Upon completion, the UI must render the `PipelineMetrics` (Latency, RAG Relevancy, MCP Success, Instruction Score) on screen.
*   **FR-5.4**: The system shall include a context-aware Safety Copilot chatbot that remembers the current formulation context across multi-turn conversations.

### FR-6: Offline Evaluation Benchmarking
*   **FR-6.1**: A dedicated benchmarking pipeline shall read from `benchmark_dataset.jsonl`.
*   **FR-6.2**: The benchmark suite shall use `ragas` connected to Google Gemini to evaluate the RAG pipeline's context retrieval accuracy and the LLM's faithfulness, dumping results to `evaluation_results.json`.

### FR-7: Fail-Closed Safety Behavior
*   **FR-7.1**: The system shall be fail-closed: a chemical or hardware item with no evaluable regulatory data shall default to `REVIEW_REQUIRED` status — never `COMPLIANT` or `SAFE`.
*   **FR-7.2**: Pydantic model defaults for `ChemicalFlag.status` and `HardwareFlag.status` shall be `REVIEW_REQUIRED`, not `COMPLIANT` or `SAFE`.
*   **FR-7.3**: The safety guardrail layer in the Supervisor shall enforce that chemical compliance, hardware compatibility, and PubChem intelligence checks always execute — even if the ReAct loop model selects `finish_audit` prematurely. Guardrail-enforced steps shall be tagged with `action_source: 'guardrail_override'` in the execution trace.

---

## 5. Non-Functional Requirements

### NFR-1: Performance & Latency
*   **API Response Time**: Basic audits shall resolve in under 2.5 seconds.
*   **Caching**: A semantic caching layer (`cache.db`) must return identical historical queries in under 50 milliseconds.

### NFR-2: Thread Safety & Concurrency
*   **Database Reliability**: The local SQLite semantic cache must implement Write-Ahead Logging (`WAL`) to prevent database locks during highly concurrent asynchronous agent operations.

### NFR-3: Security & Observability
*   **Secret Management**: LLM and search API keys must strictly reside in `.env` configurations.
*   **Logging**: All agent interactions must be trace-logged into the system's runtime memory and exposed via the SSE stream for full observability.

---

## 6. System Interfaces & REST APIs

| Endpoint | Method | Payload | Description |
|---|---|---|---|
| `/` | GET | None | Serves the main Single Page Application |
| `/api/v1/stream` | GET | `input_text`, `intent`, `region`, `language` | SSE Stream for real-time progress and trace logs |
| `/api/v1/audit` | POST | `{user_input, intent, region, language}` | Returns the full `AgentRunResult` and JSON metrics |
| `/api/v1/chat` | POST | `{message, history, formulation_context}` | Context-aware Safety Copilot chat endpoint |
| `/api/v1/examples` | GET | None | Fetches pre-configured test scenarios for the UI |
