# ChemShield AI - Setup & Installation Guide

This guide provides step-by-step instructions for setting up, configuring, running, and testing ChemShield AI locally or in an evaluation environment.

---

## Prerequisites

1. **Python 3.11 or higher**:
   Verify your Python installation:
   ```bash
   python --version
   ```
2. **API Keys**:
   - **Google Gemini API Key**: Required for multi-agent reasoning and SDS authoring. Obtain from Google AI Studio.
   - **Tavily Search API Key**: Required for live web regulatory lookups when chemicals are not indexed locally. Obtain from Tavily AI dashboard.

---

## Step-by-Step Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd L2_Project
```

### 2. Create and Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and supply your actual credentials:
```env
# --- Required ---
GEMINI_API_KEY=your_actual_gemini_api_key
TAVILY_API_KEY=your_actual_tavily_api_key

# --- Optional (defaults shown) ---
CHROMA_PERSIST_DIR=./chroma_db
HOST=127.0.0.1
PORT=7860
LLM_PROVIDER=gemini

# --- Testing (offline unit test isolation) ---
# Set TESTING=1 to disable live API calls in test environment
# TESTING=1
```

> **Note**: `TAVILY_API_KEY` is optional if you only use chemicals covered by `MASTER_CHEMICAL_DATABASE` (the 22 hardcoded OSHA chemicals). The system will use Gemini AI knowledge as fallback before attempting web search.

### 5. Ingest Regulatory Knowledge Base (RAG)
Populate ChromaDB vector database with OSHA safety standards and regulatory thresholds:
```bash
python -m src.scripts.ingest --reset
```

---

## Running the Application

### Development Server (with Uvicorn / Live Reload)
```bash
python run.py
```

Or directly via Uvicorn:
```bash
uvicorn src.api.server:app --reload --host 127.0.0.1 --port 7860
```

Open your browser and navigate to:
`http://localhost:7860/`

---

## Running Automated Tests

ChemShield AI includes a comprehensive suite of unit tests. Run the test modules using Python's standard `unittest` runner:

### 1. Test System Functions, Cache, GHS Rules, & Copilot
```bash
python -m unittest tests/test_all_functions.py
```

### 2. Test Formulation Compliance Auditing
```bash
python -m unittest tests/test_formulations.py
```

### 3. Test PubChem API Integration & 16-Section SDS Generation
```bash
python -m unittest tests/test_sds_generation.py
```

---

## Running Offline Evaluation Benchmark

Run the RAGAS-based benchmark suite against the ground-truth test dataset:
```bash
python -m src.scripts.run_benchmark
```

Results are written to `evaluation_results.json` in the project root. The benchmark evaluates:
- RAG Context Precision
- Answer Relevancy
- LLM Faithfulness
- MCP tool success rate
- End-to-end pipeline latency

---

## Test Environment Isolation

To prevent unit tests from making live API calls (Gemini, Tavily, PubChem), set the `TESTING` environment variable before running tests:

**Windows (PowerShell):**
```powershell
$env:TESTING="1"
python -m unittest discover tests/
```

**Linux / macOS:**
```bash
TESTING=1 python -m unittest discover tests/
```

---

## API Endpoints Reference

- `GET /` - Serves the ChemShield AI web application user interface.
- `GET /api/v1/stream?input_text=...&intent=audit_and_sds&region=US&language=en` - Real-time Server-Sent Events (SSE) execution stream.
- `POST /api/v1/audit` - Synchronous audit endpoint. Body: `{user_input, intent, region, language}`
- `POST /api/v1/chat` - Context-aware Safety Copilot chatbot endpoint. Body: `{message, history, formulation_context}`
- `GET /api/v1/examples` - Returns pre-configured chemical formulation scenario presets.
- `GET /docs` - Interactive FastAPI OpenAPI documentation interface.
