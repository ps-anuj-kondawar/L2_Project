# Software Requirements Specification (SRS)

**Project Name:** ChemShield AI — Chemical Safety & SDS Platform  
**Specification Version:** 2.0.0 (Production Specifications)  
**Document Status:** Approved & Implemented  

---

## 1. Executive Summary & Purpose

ChemShield AI is an automated multi-agent chemical safety compliance auditor and GHS Safety Data Sheet (SDS) authoring system. The system ingests raw laboratory formulation notes, extracts chemical ingredients and laboratory hardware configurations, audits them against regulatory safety standards, and generates 16-section OSHA HazCom 2012 / GHS Rev.9 compliant Safety Data Sheets.

---

## 2. Functional Requirements

### FR-1: Formulation Input & Entity Extraction
- **FR-1.1**: The system shall accept plain text formulation notes containing chemical names, volume/mass ratios, hardware container types, and target operating temperatures.
- **FR-1.2**: The system shall parse and extract individual chemical entities, concentrations (e.g. `%`, `ppm`), hardware container names, and target temperatures in Celsius.
- **FR-1.3**: The system shall perform fuzzy matching and automatic spelling correction for chemical names (e.g. `benzen` -> `Benzene`) and equipment types (e.g. `soda glass` -> `soda lime glass beaker`).

### FR-2: Multi-Agent Regulatory Compliance Audit
- **FR-2.1**: The `IntelligenceAgent` shall query the PubChem PUG REST API to fetch official CAS registration numbers, GHS pictogram codes, signal words (`DANGER`, `WARNING`), and hazard statements.
- **FR-2.2**: The `ChemicalAgent` shall query a local ChromaDB vector database (populated with OSHA regulatory standards) to verify concentration levels against Permissible Exposure Limits (PELs).
- **FR-2.3**: If vector retrieval precision falls below threshold, the `ChemicalAgent` shall execute a web search fallback via the Tavily API.
- **FR-2.4**: The `HardwareAgent` shall audit equipment thermal limits using an in-memory dictionary fast-path and Model Context Protocol (MCP) tool server invocation.
- **FR-2.5**: The system shall compute an overall safety verdict:
  - `APPROVED`: All chemicals comply with OSHA limits and hardware operates within safe thermal limits.
  - `PARTIAL`: Exposure limit warnings or boiling hazard risks detected.
  - `REJECTED`: Severe exposure limit violations or unsafe container temperatures detected.

### FR-3: Intent-Driven Pipeline Execution
- **FR-3.1**: The system shall support `intent="audit"` to execute entity extraction, multi-agent compliance auditing, safety verdict calculation, and LLM summary generation in ~1 second.
- **FR-3.2**: The system shall support `intent="sds"` to generate a complete 16-section GHS SDS document on demand.
- **FR-3.3**: When `intent="sds"` is requested for an audited formulation, the system shall reuse the cached audit state, skipping redundant entity extraction and network calls.

### FR-4: GHS SDS Authoring & Automated Quality Assurance
- **FR-4.1**: The `SDSAuthorAgent` shall synthesize formulation data, PubChem records, and compliance flags into a 16-section GHS SDS document.
- **FR-4.2**: The `ReflectionAgent` shall audit generated SDS documents for structural completeness, signal word consistency, and hazard statement alignment, triggering automated self-correction loops if defects are detected (max 2 iterations).

### FR-5: User Interface & Telemetry
- **FR-5.1**: The web interface shall feature a two-column workspace layout with a right-hand sticky execution telemetry sidebar.
- **FR-5.2**: The sidebar shall display a pulsing live execution status dot (`● LIVE`) and a 4-stage progress tracker (`Entity Extraction`, `Multi-Agent Audit`, `Safety Verdict`, `GHS SDS Authoring`).
- **FR-5.3**: The sidebar shall stream Server-Sent Events (SSE) log messages in real time.
- **FR-5.4**: The system shall display an automated SDS Worker Modal Preview whenever an SDS is generated.
- **FR-5.5**: Document printing shall use an isolated hidden iframe with `print-color-adjust: exact` to render full-color 16-section SDS documents.

### FR-6: Safety Copilot
- **FR-6.1**: The system shall provide an interactive Safety Copilot chatbot.
- **FR-6.2**: The copilot shall automatically inject the active session formulation context into chat prompts to answer follow-up safety questions without requiring re-typing.

---

## 3. Non-Functional Requirements

### NFR-1: Performance & Latency
- Compliance Audit (`intent="audit"`) execution time shall not exceed 2.5 seconds on un-cached requests.
- Semantic cache hits shall respond in under 0.05 seconds (50 ms).

### NFR-2: Reliability & Concurrency
- SQLite database operations shall use Write-Ahead Logging (`WAL` mode) and connection pooling (`threading.local()`) to guarantee thread safety under concurrent requests.

### NFR-3: Security & Data Hygiene
- API keys shall be stored strictly in environment variables (`.env`) and never committed to source control.
- Input validation shall sanitize user prompt strings before LLM execution.
- Codebase, comments, and documentation shall contain zero emojis.

---

## 4. System Interfaces & APIs

| Endpoint | Method | Input Payload | Output Response | Description |
|---|---|---|---|---|
| `/` | GET | None | HTML | Serves ChemShield AI web application |
| `/api/v1/stream` | GET | `input_text`, `intent` | SSE Stream | Real-time log stream and progress events |
| `/api/v1/audit` | POST | `{user_input, intent}` | JSON | Blocking compliance audit response |
| `/api/v1/chat` | POST | `{message, history, formulation_context}` | JSON | Safety copilot chatbot endpoint |
| `/api/v1/examples` | GET | None | JSON | Scenario presets |
