import logging
import sys

# Single module-level logger used across all agents.
# The server attaches per-request handlers (QueueHandler / BufferHandler)
# to this logger at request time, so every logger.info() call anywhere
# in the pipeline automatically reaches the SSE stream or response buffer.

logger = logging.getLogger("safety_auditor")
logger.setLevel(logging.INFO)
logger.propagate = False

_formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")

# Console handler so logs still appear in the terminal during development
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_formatter)
logger.addHandler(_console_handler)

