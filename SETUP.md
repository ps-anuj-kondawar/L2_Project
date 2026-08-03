# Setup & Installation Guide

This guide walks you through setting up, configuring, and running ChemShield AI locally or in production.

---

## Prerequisites

1. **Python 3.11+**: Ensure Python 3.11 or higher is installed.
   ```bash
   python --version
   ```
2. **API Keys**:
   - **Google Gemini API Key**: Obtain from Google AI Studio.
   - **Tavily Search API Key**: Obtain from Tavily AI dashboard.

---

## Step-by-Step Local Setup

### 1. Clone the Repository
```bash
git clone <your-repository-url>
cd L1_Project
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
Copy `.env.example` to `.env` and fill in your actual credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```env
GEMINI_API_KEY=your_actual_gemini_api_key
TAVILY_API_KEY=your_actual_tavily_api_key
CHROMA_PERSIST_DIR=./chroma_db
HOST=127.0.0.1
PORT=7860
```

---

## Running the Application

### Development Mode (with Live Reloading)
```bash
python run.py
```
Or directly with Uvicorn:
```bash
uvicorn src.api.server:app --reload --host 127.0.0.1 --port 7860
```

Access the application in your browser at:
`http://localhost:7860/`

---

## API Endpoints

- `GET /` — Serves the ChemShield AI web application interface.
- `GET /api/v1/stream?input_text=...&intent=audit` — Server-Sent Events (SSE) real-time pipeline execution stream.
- `POST /api/v1/audit` — Blocking audit endpoint returning structured JSON compliance report.
- `POST /api/v1/chat` — Context-aware Safety Copilot chatbot endpoint.
- `GET /api/v1/examples` — Returns pre-configured chemical formulation scenario presets.
- `GET /docs` — FastAPI Interactive OpenAPI documentation.
