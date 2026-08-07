from enum import Enum
from pydantic import BaseModel, Field

class Intent(str, Enum):
    AUDIT = "audit"
    SDS = "sds"
    FULL = "full"
    AUDIT_AND_SDS = "audit_and_sds"

class ExtractedChemical(BaseModel):
    name: str = Field(description="Name of the chemical")
    concentration: str | None = Field(default=None, description="Detected concentration, e.g., '12%' or '500 ppm'")

class ExtractedHardware(BaseModel):
    name: str = Field(description="Name of the container or equipment")
    target_temperature_celsius: float | None = Field(default=None, description="Target operating temperature in Celsius")


class ChemicalFlag(BaseModel):
    chemical_name: str = Field(
        description="The name of the chemical as found in the user input."
    )
    is_compliant: bool = Field(
        description="True if detected concentration is within regulatory limits, False otherwise."
    )
    status: str = Field(
        default="COMPLIANT",
        description="'COMPLIANT', 'NON_COMPLIANT', 'UNKNOWN', or 'REVIEW_REQUIRED'"
    )
    detected_concentration: str | None = Field(
        default=None,
        description="The concentration as stated in the user input (e.g., '6%' or '500 ppm')."
    )
    regulatory_limit: str = Field(
        description=(
            "The permissible exposure limit from the regulatory database (e.g., '1 ppm TWA'), "
            "or 'Unknown: No regulatory data found' if the chemical is not in the database."
        )
    )
    source_citation: str = Field(
        description=(
            "The exact text chunk retrieved from ChromaDB that supports this ruling."
        )
    )

class HardwareFlag(BaseModel):
    equipment_name: str = Field(
        description="The name of the container or equipment as mentioned in the user input."
    )
    target_temperature_celsius: float | None = Field(
        default=None,
        description="The target operating temperature in Celsius as stated in the user input."
    )
    max_safe_temperature_celsius: float = Field(
        description="The maximum safe operating temperature for this equipment, from the MCP server."
    )
    is_safe: bool = Field(
        description=(
            "True if target_temperature_celsius <= max_safe_temperature_celsius, False otherwise."
        )
    )
    status: str = Field(
        default="SAFE",
        description="'SAFE', 'UNSAFE', 'UNKNOWN', or 'REVIEW_REQUIRED'"
    )

class PipelineMetrics(BaseModel):
    rag_context_relevancy: float = Field(
        description="RAG Context Relevancy score: percentage of retrieved regulatory docs containing the chemical name (0.0 to 1.0)."
    )
    agent_tool_call_success_rate: float = Field(
        description="Agent Tool Call Success Rate: percentage of hardware checks completed via live MCP without fallback (0.0 to 1.0)."
    )
    llm_instruction_following: float = Field(
        description="LLM Instruction Following score: 1.0 if output matches all constraints (no bullets, single sentence), 0.0 otherwise."
    )
    total_latency: float = Field(
        description="Total round-trip latency of the pipeline in seconds."
    )

class ComplianceReport(BaseModel):
    chemical_flags: list[ChemicalFlag] = Field(
        description="One ChemicalFlag entry for each chemical identified in the user input."
    )
    hardware_flags: list[HardwareFlag] = Field(
        description="One HardwareFlag entry for each container or equipment mentioned in the user input."
    )
    overall_approval_status: str = Field(
        description=(
            "'APPROVED' if all checks pass. "
            "'REJECTED' if any check fails or there is a severe hazard. "
            "'PARTIAL' if mixed or secondary risks. "
            "'REVIEW_REQUIRED' if extraction/MCP failure or unknown chemical occurs."
        )
    )
    summary: str = Field(
        description="A single sentence summarising the overall compliance finding, explicitly mentioning any boiling point or secondary hazards if present."
    )
    metrics: PipelineMetrics = Field(
        description="Evaluation and performance metrics for the pipeline run."
    )
    correction_notes: list[str] = Field(
        default_factory=list,
        description="Auto-correction messages when chemical names were fuzzy-matched."
    )
    boundary_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings for physically impossible or contradictory input values."
    )
    cache_status: str = Field(
        default="Cold Start",
        description="Indicates whether the report was retrieved from cache or required a full pipeline run."
    )
    llm_provider_used: str = Field(
        default="Google Gemini",
        description="The actual LLM provider used to generate the report."
    )


class PubChemData(BaseModel):
    chemical_name: str
    cid: int | None = None
    cas_number: str | None = None
    molecular_weight: float | None = None
    boiling_point_celsius: float | None = None
    flash_point_celsius: float | None = None
    density: float | None = None
    signal_word: str | None = None
    ghs_pictogram_codes: list[str] = Field(default_factory=list)
    hazard_statements: list[str] = Field(default_factory=list)
    precautionary_statements: list[str] = Field(default_factory=list)
    source: str = Field(default="PubChem PUG REST API")


class SDSSection(BaseModel):
    section_number: int = Field(description="1 to 16")
    title: str = Field(description="Standard OSHA/GHS section title")
    content: str = Field(description="Structured text content of the section")


class SDSDocument(BaseModel):
    product_name: str
    revision_date: str
    prepared_by: str = "ChemShield AI Multi-Agent Platform"
    sections: list[SDSSection] = Field(default_factory=list)
    pictogram_codes: list[str] = Field(default_factory=list)
    signal_word: str = "WARNING"


class TraceStep(BaseModel):
    agent: str
    action: str
    observation: str
    timestamp_ms: int
    duration_ms: int = 0
    status: str = "success"


class AgentRunResult(BaseModel):
    compliance_report: ComplianceReport
    sds_document: SDSDocument | None = None
    sds_html: str | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    reflection_passed: bool = True
    reflection_iterations: int = 0
    total_latency_seconds: float = 0.0


