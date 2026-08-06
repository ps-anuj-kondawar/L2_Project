# ChemShield AI - Chemical Safety & GHS SDS Platform

ChemShield AI is an enterprise multi-agent safety intelligence platform designed to automate OSHA HazCom 2012 compliance auditing, PubChem regulatory retrieval, hardware thermal compatibility checks, and 16-section GHS Safety Data Sheet (SDS) authoring for chemical formulations.

---

## What ChemShield AI Does and Why

In industrial laboratories, chemical processing facilities, and research institutes, verifying formulation safety against OSHA regulatory permissible exposure limits (PELs) and equipment thermal boundaries is critical to prevent hazardous chemical exposure, thermal container failure, and regulatory non-compliance.

ChemShield AI automates this complex evaluation process by combining vector search (RAG) over OSHA standards, real-time PubChem API queries, container material safety checks via the Model Context Protocol (FastMCP), and LLM reasoning to produce instantaneous compliance reports and 16-section GHS-compliant Safety Data Sheets in seconds.

---

## Tech Stack

- **Core Framework**: Python 3.11 / 3.13, FastAPI, Uvicorn
- **LLM Reasoning & Authoring**: Google Gemini 2.0 Flash / OpenRouter Multi-Provider Fallback
- **Agent Architecture**: Modular Asyncio Multi-Agent Execution Framework
- **Tool Protocol**: Model Context Protocol (FastMCP) for hardware thermal compatibility lookup
- **Vector Search & Grounding**: ChromaDB (OSHA Standards Vector DB) and Tavily Web Search API
- **Chemical Data Integration**: PubChem PUG REST API
- **Caching Layer**: SQLite Two-Tier Semantic & Key-Value Caching (`cache.db`)
- **Frontend**: Responsive HTML5, Vanilla CSS Design System, ES6+ JavaScript, Server-Sent Events (SSE)
- **Testing Framework**: Python standard `unittest` and `unittest.IsolatedAsyncioTestCase`

---

## Multi-Agent Architecture Overview

```
                        +---------------------------------------+
                        |        Supervisor Agent               |
                        +---------------------------------------+
                                           |
           +-------------------------------+-------------------------------+
           |                               |                               |
           v                               v                               v
+-----------------------+       +-----------------------+       +-----------------------+
|  Intelligence Agent   |       |    Chemical Agent     |       |    Hardware Agent     |
| (PubChem REST API)    |       |  (OSHA RAG + Tavily)  |       |   (FastMCP Tool)      |
+-----------------------+       +-----------------------+       +-----------------------+
           |                               |                               |
           +-------------------------------+-------------------------------+
                                           |
                                           v
                        +---------------------------------------+
                        |    Safety Verdict & Summary Engine    |
                        +---------------------------------------+
                                           |
                                           v
                        +---------------------------------------+
                        |  SDS Authoring & Reflection Loop     |
                        |     (16-Section GHS Generator)       |
                        +---------------------------------------+
```

### Agent Roles:
1. **Supervisor Agent**: Manages state, entity extraction, intent parsing, ReAct action policy loop (`decide -> act -> observe -> finish`), and final verdict packaging.
2. **Intelligence Agent**: Queries PubChem PUG REST API for CAS numbers, GHS pictograms, signal words, and hazard statements.
3. **Chemical Agent**: Queries ChromaDB vector database for OSHA Permissible Exposure Limits (PELs); falls back to Tavily web search if unindexed.
4. **Hardware Agent**: Executes genuine Model Context Protocol (FastMCP) tool discovery and execution over stdio transport to audit container thermal limits.
5. **SDS Authoring Agent**: Synthesizes formulation data, PubChem records, and compliance flags into a 16-section GHS SDS document with multi-region regulatory compliance (US OSHA, EU REACH/CLP, JP JIS, CA WHMIS, UK GB CLP) and multi-language output (English, Spanish, French, German, Japanese).
6. **Reflection Agent**: Self-correction loop that validates GHS document completeness and structure before finalization.

---

## Features List

- **Instant Compliance Auditing**: Evaluates chemical concentrations and container operating temperatures against OSHA regulations in ~1 second.
- **Multi-Region & Multi-Language SDS Generation**: Generates 16-section GHS-compliant Safety Data Sheets customizable by regulatory authority (US OSHA, EU REACH, JP JIS, CA WHMIS, UK GB CLP) and output language.
- **Real-Time Execution Telemetry**: Right-side sidebar tracks entity extraction, multi-agent evaluation, verdict calculation, and SSE streaming log events in real time.
- **Safety Copilot**: Context-aware RAG-grounded chatbot that automatically incorporates active lab session formulations into safety responses.
- **Standalone PDF/Print Export**: Isolated print worker renders full-color 16-section GHS SDS documents ready for official printing or PDF export.
- **Two-Tier SQLite Caching**: Multi-level semantic cache prevents redundant LLM and external API calls.

---

## Test Suite & Verification

ChemShield AI includes a comprehensive, multi-layered unit test suite:

- `tests/test_all_functions.py`: Verifies GHS rule functions, cache roundtrips, Hardware Agent limits, Chemical Agent evaluations, and Copilot Chat responses.
- `tests/test_formulations.py`: Evaluates compliance auditing against diverse chemical and hardware formulation scenarios.
- `tests/test_sds_generation.py`: Verifies PubChem REST API retrieval and 16-section GHS SDS document generation.

---

## Setup & Quick Start

For detailed step-by-step instructions on setting up the environment, installing dependencies, populating ChromaDB, and running tests, please refer to [SETUP.md](SETUP.md).
