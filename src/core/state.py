import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from src.core.models import ExtractedChemical, ExtractedHardware, ChemicalFlag, HardwareFlag, TraceStep, SDSDocument


@dataclass
class AgentState:
    user_input: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    intent: str = "audit_and_sds"
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

    def add_trace(self, agent: str, action: str, observation: str, duration_ms: int = 0, status: str = "success", action_source: str = "model_selected") -> None:
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
