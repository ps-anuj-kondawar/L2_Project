import asyncio
import time
import sys
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.core.state import AgentState
from src.core.models import HardwareFlag
from src.core.constants import MCP_SERVER_SCRIPT
from src.core.logger import logger


async def _mcp_check(hw_name: str, temp: float) -> tuple[dict, bool, bool]:
    """
    Executes a genuine MCP tool call over stdio transport.
    Returns (result_dict, transport_ok, tool_domain_ok).
    All hardware checks execute strictly over MCP (no fast-path bypass).
    """
    server_params = StdioServerParameters(
        command=sys.executable, args=[MCP_SERVER_SCRIPT], env=None
    )
    logger.info(f"[HardwareAgent] MCP tool discovery & lookup for '{hw_name}' at {temp}C...")
    try:
        async with stdio_client(server_params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                
                # Dynamic Tool Discovery
                available_tools = await session.list_tools()
                tool_names = [t.name for t in available_tools.tools]
                logger.info(f"[HardwareAgent] Discovered MCP tools on server: {tool_names}")
                
                if "check_hardware_compatibility" not in tool_names:
                    return {
                        "equipment_name": hw_name,
                        "error": "Tool check_hardware_compatibility not found on server",
                        "is_safe": False,
                        "status": "REVIEW_REQUIRED"
                    }, True, False

                # Dynamic Tool Execution
                result = await session.call_tool(
                    "check_hardware_compatibility",
                    {"equipment_name": hw_name, "target_temperature_celsius": temp}
                )
                
                res_dict = json.loads(result.content[0].text) if result.content else {}
                
                if "error" in res_dict:
                    logger.warning(f"[HardwareAgent] MCP domain error for '{hw_name}': {res_dict['error']}")
                    res_dict["status"] = "REVIEW_REQUIRED"
                    res_dict["max_safe_temperature_celsius"] = 0.0
                    res_dict["is_safe"] = False
                    return res_dict, True, False
                
                res_dict["status"] = "SAFE" if res_dict.get("is_safe") else "UNSAFE"
                return res_dict, True, True
    except Exception as e:
        logger.error(f"[HardwareAgent] MCP transport error for '{hw_name}' ({type(e).__name__}): {e}")
        return {
            "equipment_name": hw_name,
            "target_temperature_celsius": temp,
            "max_safe_temperature_celsius": 0.0,
            "is_safe": False,
            "status": "REVIEW_REQUIRED",
            "error": f"MCP Transport Error: {type(e).__name__}"
        }, False, False


async def run_hardware_agent(state: AgentState) -> AgentState:
    """
    Hardware Compliance Agent.
    Evaluates equipment thermal limits via FastMCP tool calls concurrently.
    Fail-closed: returns REVIEW_REQUIRED on transport or domain failure.
    """
    start_time = time.time()
    if not state.hardware:
        state.add_trace(
            agent="HardwareComplianceAgent",
            action="Hardware Thermal Audit",
            observation="No hardware equipment specified in user input.",
            duration_ms=int((time.time() - start_time) * 1000),
            status="success"
        )
        return state

    logger.info(f"[HardwareAgent] Evaluating {len(state.hardware)} hardware items via MCP...")
    tasks = [_mcp_check(h.name, h.target_temperature_celsius) for h in state.hardware]
    results = await asyncio.gather(*tasks)

    flags = []
    any_transport_fail = False
    any_domain_fail = False

    for (res, transport_ok, tool_ok), h in zip(results, state.hardware):
        if not transport_ok:
            any_transport_fail = True
        if not tool_ok:
            any_domain_fail = True

        max_t = res.get("max_safe_temperature_celsius", 0.0)
        is_safe = res.get("is_safe", False)
        status = res.get("status", "REVIEW_REQUIRED")

        flags.append(HardwareFlag(
            equipment_name=h.name,
            target_temperature_celsius=h.target_temperature_celsius,
            max_safe_temperature_celsius=max_t,
            is_safe=is_safe,
            status=status
        ))

    state.hardware_flags = flags
    unsafe = [f.equipment_name for f in flags if f.status in ("UNSAFE", "REVIEW_REQUIRED")]
    obs = f"Evaluated {len(flags)} hardware items via FastMCP stdio tool discovery. Unsafe/Review: {unsafe if unsafe else 'None'}"

    trace_status = "error" if unsafe else "success"
    state.add_trace(
        agent="HardwareComplianceAgent",
        action=f"FastMCP Hardware Check ({len(flags)} items)",
        observation=obs,
        duration_ms=int((time.time() - start_time) * 1000),
        status=trace_status
    )
    return state

