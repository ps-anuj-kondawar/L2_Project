import os
import sys
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("Launching ChemShield AI FastAPI Platform on http://127.0.0.1:7860...")
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=7860, reload=True)
