"""
ChemShield AI — Unified Logging Subsystem.

Provides a centralized logger instance ('safety_auditor') shared across all agents.
Supports dynamic per-request handler attachment for:
- Live streaming SSE telemetry to front-end clients
- In-memory buffered capture for synchronous REST endpoints
- Standard console stream formatting for developer debugging
"""

import logging
import sys

logger = logging.getLogger("safety_auditor")
logger.setLevel(logging.INFO)
logger.propagate = False

_formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")

# Console handler so logs still appear in the terminal during development
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_formatter)
logger.addHandler(_console_handler)

