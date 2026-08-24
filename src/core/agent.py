"""
ChemShield AI — Legacy Core Agent Compatibility Shim.

Provides backwards-compatible re-exports for external test scripts and harnesses.
The monolithic audit pipeline is superseded by `src.agents.supervisor.run_supervisor`,
and Copilot functionality is located in `src.core.copilot.copilot_chat`.
"""

from src.core.copilot import copilot_chat  # noqa: F401

