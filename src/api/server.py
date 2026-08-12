import asyncio
import os
import json
import logging
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agents.supervisor import run_supervisor
from src.core.copilot import copilot_chat
from src.infrastructure.pdf_generator import generate_sds_pdf
from src.core.logger import logger

app = FastAPI(
    title="ChemShield AI — Enterprise Safety & SDS Platform",
    description="Multi-agent OSHA compliance auditing, PubChem GHS retrieval, and 16-section SDS generation API.",
    version="2.0.0"
)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

os.makedirs("static", exist_ok=True)
os.makedirs("assets/pictograms", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "2000"))
import re


from src.core.models import Intent

class AuditRequest(BaseModel):
    user_input: str = Field(description="Lab formulation note or chemical input text")
    intent: Intent = Field(default=Intent.AUDIT, description="Action intent: 'audit', 'sds', 'full', or 'audit_and_sds'")
    region: str = Field(default="US", description="Regulatory jurisdiction region (e.g. US, EU, JP)")
    language: str = Field(default="en", description="Output language (e.g. en, es, fr, de, ja)")


class ChatRequest(BaseModel):
    message: str
    history: list = Field(default_factory=list)
    formulation_context: str | None = Field(
        default=None,
        description="Last audited formulation text, injected into copilot system prompt for contextual awareness."
    )
    audit_summary: str | None = Field(
        default=None,
        description="Summary sentence from the last audit run, provided as context to the copilot."
    )


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>ChemShield AI is starting up...</h1>")


_EXAMPLE_SCENARIOS = {
    "rejected_benzene": {
        "title": "REJECTED: Benzene + Unsafe Soda Lime Glass",
        "input": "Formula B: 94% Water, 6% Benzene. Heat the mixture to 120°C in a soda lime glass beaker.",
    },
    "approved_ipa": {
        "title": "APPROVED: Safe Isopropanol Solvents",
        "input": "Mix 70% Isopropanol and 30% Water. Store in a polypropylene container at 25°C.",
    },
    "partial_toluene": {
        "title": "PARTIAL: Toluene & Acetone Exposure Warning",
        "input": "Formulation: 500 ppm Toluene, 800 ppm Acetone. Heated to 90°C in a polypropylene container.",
    },
    "chloroform_web": {
        "title": "Web Fallback: Chloroform Lookup",
        "input": "Formula X: 50% Chloroform. Store at 25°C in a borosilicate glass beaker.",
    },
    "typo_auto_correct": {
        "title": "Auto Correction: Fuzzy Match (benzen -> Benzene)",
        "input": "Note: Contains 6% benzen. Heated to 50°C in a borosilicate glass beaker.",
    },
}


@app.get("/api/v1/examples")
async def get_examples():
    return JSONResponse(content=_EXAMPLE_SCENARIOS)


@app.post("/api/v1/audit")
async def audit_endpoint(req: AuditRequest):
    """Blocking audit endpoint. Collects logs via a temporary handler and returns them with the result."""
    if not req.user_input or not req.user_input.strip():
        raise HTTPException(status_code=400, detail="Formulation input text cannot be empty.")
    if len(req.user_input.strip()) > MAX_INPUT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Input text exceeds maximum length of {MAX_INPUT_LENGTH} characters.")

    log_buffer: list[str] = []
    handler = _make_buffer_handler(log_buffer)
    logger.addHandler(handler)
    try:
        result = await run_supervisor(req.user_input.strip(), intent=req.intent, region=req.region, language=req.language)
        payload = result.model_dump()
        payload["logs"] = log_buffer[:]
        return JSONResponse(content=payload)
    except Exception as e:
        logger.error(f"audit_endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        logger.removeHandler(handler)


@app.get("/api/v1/stream")
async def stream_audit_endpoint(input_text: str, intent: Intent = Intent.AUDIT, region: str = "US", language: str = "en"):
    """
    Server-Sent Events endpoint.
    Attaches a per-request QueueHandler to the shared logger so every logger.info() call
    is forwarded into the SSE stream in real-time as the pipeline runs.
    """
    if not input_text or not input_text.strip():
        raise HTTPException(status_code=400, detail="Input text required.")
    if len(input_text.strip()) > MAX_INPUT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Input text exceeds maximum length of {MAX_INPUT_LENGTH} characters.")

    log_queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    queue_handler = _make_queue_handler(log_queue, loop)
    logger.addHandler(queue_handler)

    async def event_generator():
        yield _sse("start", {"message": f"Initializing ChemShield AI pipeline (intent='{intent}', region='{region}', lang='{language}')..."})

        result_holder: dict = {}
        error_holder: dict = {}

        async def run_pipeline():
            try:
                result = await run_supervisor(input_text.strip(), intent=intent, region=region, language=language)
                result_holder["result"] = result
            except Exception as exc:
                error_holder["error"] = str(exc)
            finally:
                logger.removeHandler(queue_handler)
                await log_queue.put(None)  # sentinel

        task = asyncio.create_task(run_pipeline())

        # Stream log lines until sentinel
        while True:
            try:
                msg = await asyncio.wait_for(log_queue.get(), timeout=120.0)
                if msg is None:
                    break
                yield _sse("log", {"message": msg})
            except asyncio.TimeoutError:
                yield _sse("heartbeat", {"message": "Pipeline running..."})

        await task

        if error_holder:
            yield _sse("error", {"error": error_holder["error"]})
            return

        result = result_holder.get("result")
        if not result:
            yield _sse("error", {"error": "No result returned from pipeline."})
            return

        # Stream trace steps with brief animation delay
        for step in result.trace:
            yield _sse("step", step.model_dump())
            await asyncio.sleep(0.04)

        payload = result.model_dump()
        yield _sse("result", payload)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


_SANITISE_CONTEXT_PATTERN = re.compile(r"[<>{}\[\]]")


@app.post("/api/v1/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Multi-turn safety copilot chat.
    Accepts optional formulation_context and audit_summary to make the copilot
    context-aware of the last audited formulation without the user re-typing it.
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    
    sanitised_context = None
    if req.formulation_context:
        sanitised_context = _SANITISE_CONTEXT_PATTERN.sub("", req.formulation_context)[:500]

    try:
        res_dict = await copilot_chat(
            message=req.message.strip(),
            history=req.history,
            formulation_context=sanitised_context,
            audit_summary=req.audit_summary,
        )
        return JSONResponse(content=res_dict)
    except Exception as e:
        logger.error(f"chat_endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/sds/pdf")
async def download_sds_pdf(req: AuditRequest):
    """
    Generate and download a full multi-page PDF document for a 16-section GHS Safety Data Sheet.
    """
    if not req.user_input or not req.user_input.strip():
        raise HTTPException(status_code=400, detail="Input text cannot be empty.")
    if len(req.user_input) > MAX_INPUT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Input text exceeds maximum length of {MAX_INPUT_LENGTH} characters.")

    try:
        result = await run_supervisor(
            req.user_input.strip(),
            intent=Intent.FULL,
            region=req.region,
            language=req.language
        )
        if not result.sds_document:
            raise HTTPException(status_code=400, detail="Could not generate SDS document for this formulation.")

        warning_notes = []
        if result.compliance_report.boundary_warnings:
            warning_notes.extend(result.compliance_report.boundary_warnings)
        if not result.reflection_passed:
            warning_notes.append("Automated reflection review flagged compliance items. Expert CSP review required.")

        seen = set()
        unique_notes = []
        for note in warning_notes:
            if note and note not in seen:
                seen.add(note)
                unique_notes.append(note)

        warning_msg = "\n• ".join(unique_notes) if unique_notes else None
        if warning_msg and not warning_msg.startswith("• "):
            warning_msg = "• " + warning_msg

        pdf_bytes = generate_sds_pdf(result.sds_document, warning_banner=warning_msg)
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', result.sds_document.product_name)
        filename = f"SDS_{safe_name}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"download_sds_pdf error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _make_buffer_handler(target: list[str]) -> logging.Handler:
    """Returns a handler that appends formatted log lines to a list."""
    class _BufferHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            target.append(self.format(record))

    h = _BufferHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", "%H:%M:%S"))
    return h


def _make_queue_handler(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> logging.Handler:
    """Returns a handler that pushes formatted log lines into an asyncio queue (thread-safe)."""
    class _QueueHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = self.format(record)
            try:
                loop.call_soon_threadsafe(queue.put_nowait, msg)
            except Exception:
                pass

    h = _QueueHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", "%H:%M:%S"))
    return h
