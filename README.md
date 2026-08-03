# ChemShield AI — Chemical Safety & GHS SDS Platform

ChemShield AI is an enterprise multi-agent safety intelligence platform designed to automate OSHA HazCom 2012 compliance auditing, PubChem regulatory retrieval, hardware thermal compatibility checks, and 16-section GHS Safety Data Sheet (SDS) authoring for chemical formulations.

---

## Technical Stack

- **Core Framework**: Python 3.11+ / FastAPI
- **LLM Reasoning & Synthesis**: Google Gemini
- **Agent Orchestration**: Modular Asyncio Multi-Agent Architecture
- **Tool Protocol**: Model Context Protocol (FastMCP) for hardware compatibility lookup
- **Vector Search & Grounding**: ChromaDB (OSHA Standards Vector DB) + Tavily Web Search API
- **Chemical Data Integration**: PubChem PUG REST API
- **Caching Layer**: SQLite Two-Tier Semantic & Key-Value Caching (`cache.db`)
- **Frontend**: HTML5, Vanilla CSS Design System, JavaScript (ES6+), Server-Sent Events (SSE)

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
1. **Supervisor Agent**: Manages state, entity extraction, intent parsing, agent dispatch, and final verdict packaging.
2. **Intelligence Agent**: Queries PubChem PUG REST API for CAS numbers, GHS pictograms, signal words, and hazard statements.
3. **Chemical Agent**: Queries ChromaDB vector database for OSHA Permissible Exposure Limits (PELs); falls back to Tavily web search if unindexed.
4. **Hardware Agent**: Fast-path dictionary lookup and FastMCP tool server invocation to audit container thermal limits.
5. **SDS Authoring Agent**: Synthesizes formulation data, PubChem records, and compliance flags into a 16-section GHS SDS document.
6. **Reflection Agent**: Self-correction loop that validates GHS document completeness and structure before finalization.

---

## Key Features

- **Instant Compliance Auditing**: Evaluates chemical concentrations and container operating temperatures against OSHA regulations in ~1 second.
- **Decoupled On-Demand SDS Generation**: Generates 16-section GHS-compliant Safety Data Sheets on demand using cached compliance audit data.
- **Real-Time Execution Telemetry**: Right-side sidebar tracks entity extraction, multi-agent evaluation, verdict calculation, and SSE streaming log events in real time.
- **Safety Copilot**: Context-aware RAG-grounded chatbot that automatically incorporates active lab session formulations into safety responses.
- **Standalone PDF/Print Export**: Isolated print worker renders full-color 16-section GHS SDS documents ready for official printing or PDF export.
- **Two-Tier SQLite Caching**: Multi-level semantic cache prevents redundant LLM and external API calls.
