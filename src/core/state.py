"""
ChemShield AI — Shared Blackboard State Data Model.

This module defines the central AgentState dataclass, which acts as the shared
blackboard across all cooperating agents in the multi-agent architecture:
- SupervisorAgent (orchestration, Cas lookup, entity extraction)
- IntelligenceAgent (PubChem API property and GHS hazard retrieval)
- ChemicalAgent (5-tier OSHA and regulatory exposure evaluation)
- HardwareAgent (MCP thermal boundary validation)
- SDSAuthorAgent (16-section GHS Safety Data Sheet authoring)
- ReflectionAgent (automated quality gate and guardrail verification)
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.core.models import (
    ChemicalFlag,
    ExtractedChemical,
    ExtractedHardware,
    HardwareFlag,
    SDSDocument,
    TraceStep,
)


@dataclass
class AgentState:
    """
    Shared blackboard mutable state passed between pipeline agents.

    Attributes:
        user_input (str): Raw unstructured laboratory note or recipe text.
        run_id (str): Unique 8-character execution identifier for traceability.
        intent (str): Selected execution intent ('audit', 'sds', 'full', 'audit_and_sds').
        region (str): Target regulatory jurisdiction code (e.g., 'US', 'EU').
        language (str): Target document language code (e.g., 'en', 'es').
        chemicals (list[ExtractedChemical]): Extracted and normalized chemical components.
        hardware (list[ExtractedHardware]): Extracted lab equipment and temperature parameters.
        pubchem_data (dict[str, Any]): Real PubChem GHS classification and CID metadata.
        chemical_flags (list[ChemicalFlag]): Regulatory compliance decisions per chemical.
        hardware_flags (list[HardwareFlag]): Thermal compatibility rulings per container.
        sds_document (SDSDocument | None): Structured 16-section GHS Safety Data Sheet.
        sds_html (str | None): Rendered responsive HTML presentation of the SDS.
        reflection_notes (list[str]): Quality gate guardrail audit findings and critiques.
        reflection_passed (bool): Whether the generated SDS passed all 9 quality checks.
        reflection_iterations (int): Number of reflection and correction loop cycles completed.
        trace (list[TraceStep]): Structured chronological event log of agent actions.
        boundary_warnings (list[str]): Physical hazard warnings (e.g. boiling-point breach).
        overall_status (str): Aggregated safety verdict ('APPROVED', 'REJECTED', 'REVIEW_REQUIRED').
    """
    user_input: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    intent: str = "audit"
    region: str = "US"
    language: str = "en"
    chemicals: list[ExtractedChemical] = field(default_factory=list)
    hardware: list[ExtractedHardware] = field(default_factory=list)
    pubchem_data: dict[str, Any] = field(default_factory=dict)
    chemical_flags: list[ChemicalFlag] = field(default_factory=list)
    hardware_flags: list[HardwareFlag] = field(default_factory=list)
    sds_document: SDSDocument | None = None
    sds_html: str | None = None
    reflection_notes: list[str] = field(default_factory=list)
    reflection_passed: bool = True
    reflection_iterations: int = 0
    trace: list[TraceStep] = field(default_factory=list)
    boundary_warnings: list[str] = field(default_factory=list)
    overall_status: str = "PENDING"

    def add_trace(
        self,
        agent: str,
        action: str,
        observation: str,
        duration_ms: int = 0,
        status: str = "success",
        action_source: str = "model_selected"
    ) -> None:
        """
        Record a timestamped execution step into the agent state trace log.

        Args:
            agent (str): Name of the emitting agent (e.g., 'ChemicalAgent', 'Supervisor').
            action (str): Specific action or tool call executed.
            observation (str): Outcome, summary, or extracted data observation.
            duration_ms (int): Execution time in milliseconds. Defaults to 0.
            status (str): Outcome status ('success', 'failure', 'retry').
            action_source (str): Source origin ('model_selected', 'rule_engine', 'mcp').
        """
        step = TraceStep(
            agent=agent,
            action=action,
            observation=observation,
            timestamp_ms=int(time.time() * 1000),
            duration_ms=duration_ms,
            status=status,
            action_source=action_source
        )
        self.trace.append(step)
