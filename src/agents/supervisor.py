import asyncio
import re
import time
import json
from src.core.state import AgentState
from src.core.models import (
    ComplianceReport,
    PipelineMetrics,
    AgentRunResult,
    ExtractedChemical,
    ExtractedHardware
)
from src.agents.intelligence_agent import run_intelligence_agent
from src.agents.chemical_agent import run_chemical_agent
from src.agents.hardware_agent import run_hardware_agent
from src.agents.sds_author_agent import run_sds_author_agent
from src.agents.reflection_agent import run_reflection_agent
from src.utils.validator import (
    validate_and_correct_chemicals,
    validate_physical_boundaries,
    fuzzy_match_hardware
)
from src.infrastructure.llm_client import chat as llm_chat, LAST_PROVIDER_USED
from src.infrastructure.cache import (
    get_semantic_cache,
    set_semantic_cache,
    get_summary_cache,
    set_summary_cache,
    get_osha_limits
)
from src.core.logger import logger
from src.core.constants import BOILING_POINTS_CELSIUS


async def _extract_entities(text: str) -> tuple[list[ExtractedChemical], list[ExtractedHardware]]:
    schema = {
        "chemicals": [{"name": "string", "concentration": "string (e.g. '6%' or '300 ppm')"}],
        "hardware":  [{"name": "string", "target_temperature_celsius": "float"}],
    }
    prompt = (
        "Extract all chemicals, concentrations, containers, and temperatures from the text below.\n"
        f"Return ONLY valid JSON matching this schema: {json.dumps(schema)}\n\nText:\n{text}"
    )
    # Bounded repair loop for JSON parsing
    for attempt in range(2):
        try:
            raw = await llm_chat(
                messages=[
                    {"role": "system", "content": "You are a precise chemical entity extractor. Return JSON only."},
                    {"role": "user",   "content": prompt if attempt == 0 else f"{prompt}\n\nPrevious attempt failed JSON parsing. Output strictly valid JSON."}
                ],
                json_mode=True,
            )
            data = json.loads(raw)
            chems = [ExtractedChemical(name=c["name"], concentration=c.get("concentration")) for c in data.get("chemicals", []) if c.get("name")]
            hws = []
            for h in data.get("hardware", []):
                if not h.get("name"):
                    continue
                try:
                    temp_val = float(h.get("target_temperature_celsius") or 25.0)
                except (ValueError, TypeError):
                    temp_val = 25.0
                hws.append(ExtractedHardware(name=h["name"], target_temperature_celsius=temp_val))
            return chems, hws
        except Exception as e:
            logger.warning(f"[Supervisor] Entity extraction attempt {attempt + 1} failed ({type(e).__name__}): {e}")
    
    return [], []


def _evaluate_summary_quality(summary: str) -> float:
    """Return 1.0 if summary is a single sentence with no bullets or newlines, else 0.0."""
    summary = summary.strip()
    if not summary or "\n" in summary:
        return 0.0
    if any(b in summary for b in ["* ", "- ", "\u2022 "]):
        return 0.0
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', summary) if s.strip()]
    return 1.0 if len(sentences) == 1 else 0.0


async def run_supervisor(
    user_input: str,
    intent: str = "audit",
    region: str = "US",
    language: str = "en"
) -> AgentRunResult:
    """
    Supervisor Agent Orchestrator.
    Manages state, dispatches model-mediated tool choices, handles reflection loops,
    and packages final AgentRunResult.
    """
    start_time = time.time()
    logger.info(f"[Supervisor] Initializing ChemShield AI workflow (intent='{intent}', region='{region}', lang='{language}') for: '{user_input[:60]}'")

    # Step 0: Check SQLite Semantic Cache
    cached = get_semantic_cache(user_input, intent=intent, region=region, language=language)
    if not cached and intent in ("full", "sds", "audit_and_sds"):
        cached = get_semantic_cache(user_input, intent="audit", region=region, language=language)

    if cached:
        result = AgentRunResult.model_validate(cached)
        # If user requested SDS ('full'/'sds') but cache only has audit without SDS, upgrade entry using cached data
        if intent in ("full", "sds", "audit_and_sds") and not result.sds_html:
            logger.info(f"[Supervisor] Semantic cache HIT for compliance audit! Reusing audit data to generate SDS directly...")
            state = AgentState(user_input=user_input, intent=intent, region=region, language=language)
            comp = result.compliance_report
            state.chemical_flags = comp.chemical_flags
            state.hardware_flags = comp.hardware_flags
            state.overall_status = comp.overall_approval_status
            state.trace = result.trace

            state.chemicals = [ExtractedChemical(name=f.chemical_name, concentration=f.detected_concentration) for f in comp.chemical_flags]
            state.hardware = [ExtractedHardware(name=f.equipment_name, target_temperature_celsius=f.target_temperature_celsius) for f in comp.hardware_flags]

            from src.infrastructure.cache import get_pubchem_cache
            for c in state.chemicals:
                p_data = get_pubchem_cache(c.name)
                if p_data:
                    state.pubchem_data[c.name] = p_data

            await run_sds_author_agent(state)
            await run_reflection_agent(state)

            while not state.reflection_passed and state.reflection_iterations < 2:
                state.reflection_iterations += 1
                logger.info(f"[Supervisor] Reflection iteration {state.reflection_iterations}: Retrying SDS Authoring Agent...")
                await run_sds_author_agent(state)
                await run_reflection_agent(state)

            total_latency = round(time.time() - start_time, 3)
            result.sds_document = state.sds_document
            result.sds_html = state.sds_html
            result.reflection_passed = state.reflection_passed
            result.reflection_iterations = state.reflection_iterations
            result.total_latency_seconds = total_latency

            try:
                set_semantic_cache(user_input, result.model_dump_json(), intent=intent, region=region, language=language)
                logger.info("[Supervisor] Successfully upgraded cached audit entry with generated SDS.")
            except Exception as e:
                logger.warning(f"[Supervisor] Could not update cache: {e}")

            return result
        else:
            logger.info(f"[Supervisor] Cache HIT! Returning cached result for: '{user_input[:60]}'")
            result.total_latency_seconds = round(time.time() - start_time, 3)
            result.compliance_report.cache_status = "SQLite Semantic Cache Hit"
            return result

    state = AgentState(user_input=user_input, intent=intent, region=region, language=language)

    # Step 1: Entity Extraction & Validation
    chems, hws = await _extract_entities(user_input)

    chem_tuples = [(c.name, c.concentration or "") for c in chems]
    corrected_tuples, corr_notes = validate_and_correct_chemicals(chem_tuples)
    state.chemicals = [ExtractedChemical(name=c[0], concentration=c[1]) for c in corrected_tuples]

    hw_tuples = []
    for h in hws:
        c_hw = fuzzy_match_hardware(h.name)
        hw_tuples.append((c_hw, h.target_temperature_celsius))
    state.hardware = [ExtractedHardware(name=h[0], target_temperature_celsius=h[1]) for h in hw_tuples]

    logger.info(f"[Supervisor] Extracted {len(state.chemicals)} chemical(s): {[f'{c.name} ({c.concentration})' for c in state.chemicals]}, {len(state.hardware)} hardware item(s): {[f'{h.name} ({h.target_temperature_celsius}C)' for h in state.hardware]}")

    # Physical boundary warnings
    boundary_warnings = validate_physical_boundaries(
        [(c.name, c.concentration or "") for c in state.chemicals],
        [(h.name, h.target_temperature_celsius) for h in state.hardware]
    )
    if boundary_warnings:
        logger.warning(f"[Supervisor] Boundary warnings: {boundary_warnings}")

    state.add_trace(
        agent="Supervisor",
        action="Input Intent Parsing & Entity Extraction",
        observation=f"Extracted {len(state.chemicals)} chemicals and {len(state.hardware)} hardware items.",
        duration_ms=int((time.time() - start_time) * 1000),
        status="success"
    )

    # Step 2: Model-Mediated ReAct Action Loop
    # The supervisor model dynamically decides which specialist action to invoke based on current observations.
    completed_actions = set()
    observations: list[str] = []
    max_steps = 4
    step_count = 0

    while step_count < max_steps:
        step_count += 1
        available_actions = []
        if "chemical" not in completed_actions and state.chemicals:
            available_actions.append("check_chemical_compliance")
        if "hardware" not in completed_actions and state.hardware:
            available_actions.append("check_hardware_compatibility")
        if "pubchem" not in completed_actions and state.chemicals:
            available_actions.append("fetch_pubchem_intelligence")
        if "sds" not in completed_actions:
            available_actions.append("flag_sds_required")
        
        available_actions.append("finish_audit")

        if len(available_actions) == 1 and "finish_audit" in available_actions:
            logger.info("[Supervisor] All applicable tool checks completed. Finishing audit phase.")
            break

        # Model Policy Decision
        policy_prompt = (
            f"You are the Supervisor AI Policy model. Formulations Input: '{user_input}'.\n"
            f"Extracted Chemicals: {[c.name for c in state.chemicals]}.\n"
            f"Extracted Hardware: {[h.name for h in state.hardware]}.\n"
            f"Completed Actions: {list(completed_actions)}.\n"
            f"Current Observations: {observations if observations else 'None'}.\n"
            f"Available Actions: {available_actions}.\n\n"
            "Choose the next required action to take. If the user explicitly asks for an SDS or Safety Data Sheet, choose 'flag_sds_required'. Return ONLY valid JSON in format: {\"action\": \"action_name\", \"reasoning\": \"explanation\"}"
        )
        try:
            decision_raw = await llm_chat(
                messages=[
                    {"role": "system", "content": "You are a multi-agent policy router. Return JSON only."},
                    {"role": "user", "content": policy_prompt}
                ],
                json_mode=True
            )
            decision = json.loads(decision_raw)
            next_action = decision.get("action", "finish_audit")
            if next_action not in available_actions:
                logger.warning(f"[Supervisor] Invalid action '{next_action}' requested by model. Falling back to '{available_actions[0]}'.")
                next_action = available_actions[0]
        except Exception:
            next_action = available_actions[0] if available_actions else "finish_audit"

        logger.info(f"[Supervisor Loop Step {step_count}] Model selected action: '{next_action}'")

        if next_action == "finish_audit":
            break
        elif next_action == "flag_sds_required":
            completed_actions.add("sds")
            intent = "full"
            observations.append("User requested SDS generation; flagged intent='full'.")
        elif next_action == "check_chemical_compliance":
            await run_chemical_agent(state)
            completed_actions.add("chemical")
            chem_obs = [f"{f.chemical_name}: status={f.status}, limit={f.regulatory_limit}" for f in state.chemical_flags]
            observations.append(f"Chemical Compliance Audit: {chem_obs}")
        elif next_action == "check_hardware_compatibility":
            await run_hardware_agent(state)
            completed_actions.add("hardware")
            hw_obs = [f"{f.equipment_name}: status={f.status}, max_temp={f.max_safe_temperature_celsius}C" for f in state.hardware_flags]
            observations.append(f"Hardware Compatibility Audit: {hw_obs}")
        elif next_action == "fetch_pubchem_intelligence":
            await run_intelligence_agent(state)
            completed_actions.add("pubchem")
            pub_obs = [f"{c}: CID={data.get('cid')}" for c, data in state.pubchem_data.items() if isinstance(data, dict)]
            observations.append(f"PubChem Intelligence Query: {pub_obs}")
        else:
            break

    # Safety Guardrail: Execute any unperformed essential agent steps if model skipped them prior to finish
    if "chemical" not in completed_actions and state.chemicals:
        logger.info("[Supervisor Guardrail] Model skipped chemical compliance check; executing guardrail check.")
        await run_chemical_agent(state)
        state.add_trace(
            agent="Supervisor",
            action="Safety Guardrail Override (Chemical Check)",
            observation="Executed chemical compliance check required by safety policy after model finished early.",
            status="warning"
        )
    if "hardware" not in completed_actions and state.hardware:
        logger.info("[Supervisor Guardrail] Model skipped hardware compliance check; executing guardrail check.")
        await run_hardware_agent(state)
        state.add_trace(
            agent="Supervisor",
            action="Safety Guardrail Override (Hardware Check)",
            observation="Executed hardware compatibility check required by safety policy after model finished early.",
            status="warning"
        )
    if "pubchem" not in completed_actions and state.chemicals:
        logger.info("[Supervisor Guardrail] Model skipped PubChem query; executing guardrail query.")
        await run_intelligence_agent(state)
        state.add_trace(
            agent="Supervisor",
            action="Safety Guardrail Override (PubChem Fetch)",
            observation="Fetched PubChem intelligence data required for complete audit after model finished early.",
            status="warning"
        )

    # Step 3: Compute Safety Verdict (Fail-Closed)
    boiling_hazards = []
    for hw in state.hardware:
        target_temp = hw.target_temperature_celsius
        if target_temp is not None:
            for c in state.chemicals:
                bp = BOILING_POINTS_CELSIUS.get(c.name.lower())
                if bp is None:
                    bp = (get_osha_limits(c.name) or {}).get("boiling_point")
                if bp is not None and target_temp >= bp:
                    boiling_hazards.append(f"{c.name} (bp {bp}°C) heated to {target_temp}°C in {hw.name} — boiling hazard")

    any_hw_review   = any(getattr(f, "status", "") == "REVIEW_REQUIRED" or not f.is_safe for f in state.hardware_flags)
    any_chem_review = any(getattr(f, "status", "") in ("UNKNOWN", "REVIEW_REQUIRED") or not f.is_compliant for f in state.chemical_flags)

    if any_hw_review or any_chem_review:
        state.overall_status = "REJECTED" if (any(not f.is_safe for f in state.hardware_flags) or any(not f.is_compliant for f in state.chemical_flags)) else "REVIEW_REQUIRED"
    elif boiling_hazards:
        state.overall_status = "PARTIAL"
    else:
        state.overall_status = "APPROVED"

    logger.info(f"[Supervisor] Safety Verdict calculated: '{state.overall_status}' ({len(state.chemical_flags)} chemical flags, {len(state.hardware_flags)} hardware flags)")

    violation_notes = (
        [f"{f.chemical_name}: {f.detected_concentration} exceeds limit of {f.regulatory_limit}" for f in state.chemical_flags if not f.is_compliant] +
        [f"{f.equipment_name}: {f.target_temperature_celsius}C exceeds max {f.max_safe_temperature_celsius}C" for f in state.hardware_flags if not f.is_safe] +
        boiling_hazards
    )

    llm_summary_input = (
        "Violations found:\n" + "\n".join(f"- {n}" for n in violation_notes)
        if violation_notes else
        "No violations found. All safety checks passed."
    )

    # Step 4: Summary Generation (cached)
    cached_summary = get_summary_cache(violation_notes)
    if cached_summary:
        logger.info("[Supervisor] Summary Cache HIT! Reusing safety summary.")
        summary = cached_summary
    else:
        logger.info("[Supervisor] Generating safety summary via LLM...")
        summary = await llm_chat(
            messages=[
                {"role": "system", "content": "You are a lab safety officer. Write ONE concise sentence summarising safety findings."},
                {"role": "user", "content": llm_summary_input}
            ]
        )
        set_summary_cache(violation_notes, summary)

    # Step 5: SDS Generation & Reflection Loop (executed ONLY if intent is full/sds)
    if intent in ("full", "sds", "audit_and_sds"):
        logger.info("[Supervisor] Intent includes GHS SDS. Dispatching SDSAuthorAgent & Reflection...")
        await run_sds_author_agent(state)
        await run_reflection_agent(state)

        while not state.reflection_passed and state.reflection_iterations < 2:
            state.reflection_iterations += 1
            logger.info(f"[Supervisor] Reflection iteration {state.reflection_iterations}: Retrying SDS Authoring Agent...")
            await run_sds_author_agent(state)
            await run_reflection_agent(state)
    else:
        logger.info("[Supervisor] Intent is 'audit'. Skipping SDS Authoring & Reflection loop (~1s fast finish).")

    total_latency = time.time() - start_time

    # Real metric computation
    rag_hits = sum(1 for f in state.chemical_flags if f.source_citation and "Web search" not in f.source_citation)
    rag_relevancy = rag_hits / len(state.chemical_flags) if state.chemical_flags else 1.0

    mcp_hits = sum(1 for step in state.trace if "FastMCP" in step.action and step.status != "error")
    mcp_total = sum(1 for step in state.trace if "FastMCP" in step.action)
    mcp_rate = mcp_hits / mcp_total if mcp_total else 1.0

    llm_score = _evaluate_summary_quality(summary)

    metrics = PipelineMetrics(
        rag_context_relevancy=round(rag_relevancy, 2),
        agent_tool_call_success_rate=round(mcp_rate, 2),
        llm_instruction_following=llm_score,
        total_latency=round(total_latency, 3)
    )

    try:
        with open("evaluation_results.json", "w", encoding="utf-8") as f:
            json.dump(metrics.model_dump(), f, indent=4)
    except Exception as e:
        logger.warning(f"[Supervisor] Could not write to evaluation_results.json: {e}")

    comp_report = ComplianceReport(
        chemical_flags=state.chemical_flags,
        hardware_flags=state.hardware_flags,
        overall_approval_status=state.overall_status,
        summary=summary,
        metrics=metrics,
        correction_notes=corr_notes,
        boundary_warnings=boundary_warnings,
        cache_status="Multi-Agent Pipeline Run",
        llm_provider_used=LAST_PROVIDER_USED
    )

    result = AgentRunResult(
        compliance_report=comp_report,
        sds_document=state.sds_document,
        sds_html=state.sds_html,
        trace=state.trace,
        reflection_passed=state.reflection_passed,
        reflection_iterations=state.reflection_iterations,
        total_latency_seconds=total_latency
    )

    try:
        set_semantic_cache(user_input, result.model_dump_json(), intent=intent, region=region, language=language)
        logger.info("[Supervisor] Successfully saved run result to SQLite cache.")
    except Exception as e:
        logger.warning(f"[Supervisor] Could not cache result: {e}")

    return result
