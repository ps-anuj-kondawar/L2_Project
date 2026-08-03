import os
from dotenv import load_dotenv

load_dotenv(override=True)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

CHROMA_PERSIST_DIR = "./chroma_db"
CHROMA_COLLECTION_NAME = "regulatory_data"

RAG_DATA_PATH = "./data/regulatory_framework.txt"
RAG_TOP_K = 5

MCP_SERVER_SCRIPT = "src/infrastructure/mcp_server.py"

HARDWARE_LIMITS: dict[str, int] = {
    "soda-lime glass":        100,
    "borosilicate glass":     500,
    "stainless steel beaker": 600,
    "polypropylene container": 80,
}

BOILING_POINTS_CELSIUS: dict[str, float] = {
    "acetone":       56.0,
    "methanol":      65.0,
    "isopropanol":   82.0,
    "ipa":           82.0,
    "ethanol":       78.0,
    "toluene":      111.0,
    "benzene":       80.1,
}
