# This module previously contained the monolithic audit pipeline and copilot chat.
# The audit pipeline has been fully superseded by the multi-agent supervisor system.
# Copilot chat has been moved to src.core.copilot.
#
# This file is retained as a thin re-export shim so any external scripts that
# import from here continue to work without changes.

from src.core.copilot import copilot_chat  # noqa: F401
