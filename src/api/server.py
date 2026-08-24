"""
ChemShield AI — FastAPI Application Server.

Provides REST and Server-Sent Events (SSE) endpoints for:
- Automated OSHA compliance auditing and risk assessment
- Live streaming execution traces and diagnostic logs
- Context-aware multi-turn chemical safety Copilot chat
- Full 16-section GHS Safety Data Sheet (SDS) PDF generation
- Example laboratory formulation scenario catalogs

Architecture:
- Asynchronous non-blocking route handlers powered by FastAPI and Uvicorn
- Real-time logging dispatch via thread-safe QueueHandler and BufferHandler
- Strict input validation and sanitization using Pydantic V2 schemas
"""

import asyncio
import json
import logging
import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.agents.supervisor import run_supervisor
from src.core.copilot import copilot_chat
from src.core.logger import logger
from src.core.models import Intent
from src.infrastructure.pdf_generator import generate_sds_pdf

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
    """Ensure static assets are never cached during development or live evaluation."""
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
    """Favicon endpoint returning HTTP 204 No Content."""
    return Response(status_code=204)

MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "2000"))

class AuditRequest(BaseModel):
    """Request payload schema for compliance auditing and SDS generation."""
    user_input: str = Field(description="Lab formulation note or chemical input text")
    intent: Intent = Field(default=Intent.AUDIT, description="Action intent: 'audit', 'sds', 'full', or 'audit_and_sds'")
    region: str = Field(default="US", description="Regulatory jurisdiction region (e.g. US, EU, JP)")
    language: str = Field(default="en", description="Output language (e.g. en, es, fr, de, ja)")


class ChatRequest(BaseModel):
    """Request payload schema for multi-turn Copilot conversations."""
    message: str = Field(description="User prompt or safety inquiry")
    history: list = Field(default_factory=list, description="Prior conversation message turns")
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
    """
    Serve the Single Page Application (SPA) HTML entry point.
    
    Returns:
        HTMLResponse: Rendered static index.html or bootstrap status page.
    """
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
        "title": "REVIEW_REQUIRED: Toluene & Acetone Exposure Warning",
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
    """
    Retrieve pre-configured benchmark scenario catalog for UI demonstration.
    
    Returns:
        JSONResponse: Dictionary of preset test scenarios with titles and input texts.
    """
    return JSONResponse(content=_EXAMPLE_SCENARIOS)


@app.post("/api/v1/audit")
async def audit_endpoint(req: AuditRequest):
    """
    Execute a synchronous compliance audit and risk assessment pipeline run.

    Attaches a thread-scoped buffer handler to capture diagnostic log output
    and bundles logs into the final JSON payload.

    Args:
        req (AuditRequest): Audit configuration, input text, region, and language.

    Returns:
        JSONResponse: Serialized AgentRunResult including compliance report and logs.

    Raises:
        HTTPException: 400 if input is empty or exceeds character limits; 500 on execution failure.
    """
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
    Stream live execution trace steps and diagnostic logs via Server-Sent Events (SSE).

    Attaches a per-request QueueHandler to the shared logger to stream log events
    to the UI in real time as each agent executes.

    Args:
        input_text (str): Lab formulation text.
        intent (Intent): Workflow intent ('audit', 'sds', 'full', 'audit_and_sds').
        region (str): Target regulatory jurisdiction (e.g., 'US', 'EU').
        language (str): Output language code (e.g., 'en', 'es').

    Returns:
        StreamingResponse: SSE stream emitting 'start', 'log', 'step', 'result', and 'error' events.

    Raises:
        HTTPException: 400 if input text is empty or exceeds MAX_INPUT_LENGTH.
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
    Handle multi-turn interactive Copilot chat conversations.

    Injects active formulation context and audit summaries into the reasoning
    context, grounding answers against OSHA regulatory guidelines and PubChem data.

    Args:
        req (ChatRequest): Incoming user message, conversation history, and optional context.

    Returns:
        JSONResponse: Copilot response, latency metrics, and grounding precision scores.

    Raises:
        HTTPException: 400 if message is empty; 500 on server error.
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
    Generate and stream a publication-grade 16-section GHS Safety Data Sheet PDF.

    Executes full multi-agent authoring and validation, appending safety banners
    for non-compliant or reflection-flagged formulations.

    Args:
        req (AuditRequest): Request parameters with formulation text, region, and language.

    Returns:
        Response: Binary application/pdf stream with Content-Disposition attachment header.

    Raises:
        HTTPException: 400 on empty input or SDS generation failure; 500 on internal errors.
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


# ── Internal logging and SSE helpers ──────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    """
    Format a Server-Sent Event frame.

    Args:
        event (str): Event name identifier (e.g. 'log', 'step', 'result').
        data (dict): Payload dictionary serialized as JSON.

    Returns:
        str: Standard SSE formatted text chunk.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _make_buffer_handler(target: list[str]) -> logging.Handler:
    """
    Create a lightweight logging Handler that appends records to an in-memory list.

    Args:
        target (list[str]): Mutable list receiving formatted log strings.

    Returns:
        logging.Handler: Configured logging handler.
    """
    class _BufferHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            target.append(self.format(record))

    h = _BufferHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", "%H:%M:%S"))
    return h


def _make_queue_handler(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> logging.Handler:
    """
    Create a thread-safe logging Handler that pushes records into an asyncio Queue.

    Args:
        queue (asyncio.Queue): Target queue receiving formatted log messages.
        loop (asyncio.AbstractEventLoop): Event loop on which queue operations are scheduled.

    Returns:
        logging.Handler: Thread-safe queue logging handler.
    """
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
