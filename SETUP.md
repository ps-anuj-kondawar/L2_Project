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
GEMINI_API_KEY=your_actual_gemini_api_key
TAVILY_API_KEY=your_actual_tavily_api_key
CHROMA_PERSIST_DIR=./chroma_db
HOST=127.0.0.1
PORT=7860
```

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

## API Endpoints Reference

- `GET /` - Serves the ChemShield AI web application user interface.
- `GET /api/v1/stream?input_text=...&intent=audit_and_sds&region=US&language=en` - Real-time Server-Sent Events (SSE) execution stream.
- `POST /api/v1/audit` - Synchronous audit endpoint returning structured JSON compliance report.
- `POST /api/v1/chat` - Context-aware Safety Copilot chatbot endpoint.
- `GET /api/v1/examples` - Returns pre-configured chemical formulation scenario presets.
- `GET /docs` - Interactive FastAPI OpenAPI documentation interface.
