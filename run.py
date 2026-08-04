import os
import sys
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "7860"))
    reload = os.getenv("ENV", "development") == "development"
    print(f"Launching ChemShield AI FastAPI Platform on http://{host}:{port}...")
    uvicorn.run("src.api.server:app", host=host, port=port, reload=reload)
