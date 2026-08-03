import asyncio
import time
import sys
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.core.state import AgentState
from src.core.models import HardwareFlag
from src.core.constants import MCP_SERVER_SCRIPT, HARDWARE_LIMITS
from src.core.logger import logger


async def _mcp_check(hw_name: str, temp: float) -> tuple[dict, bool]:
    key = hw_name.lower().strip()

    # Fast path: if the equipment is in our local constants, skip MCP subprocess entirely
    if key in HARDWARE_LIMITS:
        max_temp = float(HARDWARE_LIMITS[key])
        logger.info(f"[HardwareAgent] Fast-path check for '{hw_name}': max={max_temp}C target={temp}C")
        return {
            "equipment_name": hw_name,
            "target_temperature_celsius": temp,
            "max_safe_temperature_celsius": max_temp,
            "is_safe": temp <= max_temp,
        }, True

    # Slow path: unknown equipment — delegate to MCP tool server
    server_params = StdioServerParameters(
        command=sys.executable, args=[MCP_SERVER_SCRIPT], env=None
    )
    logger.info(f"[HardwareAgent] MCP lookup for unknown equipment '{hw_name}' at {temp}C...")
    try:
        async with stdio_client(server_params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                result = await session.call_tool(
                    "check_hardware_compatibility",
                    {"equipment_name": hw_name, "target_temperature_celsius": temp}
                )
                res_dict = json.loads(result.content[0].text) if result.content else {}
                return res_dict, True
    except Exception as e:
        max_t = float(HARDWARE_LIMITS.get(key, 0))
        logger.warning(f"[HardwareAgent] MCP connection failed ({type(e).__name__}). Falling back to local limits: max={max_t}C")
        return {
            "equipment_name": hw_name,
            "target_temperature_celsius": temp,
            "max_safe_temperature_celsius": max_t,
            "is_safe": temp <= max_t,
        }, False


async def run_hardware_agent(state: AgentState) -> AgentState:
    """
    Hardware Compliance Agent.
    Evaluates equipment thermal limits via FastMCP tool calls concurrently.
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
    for (res, mcp_ok), h in zip(results, state.hardware):
        max_t = res.get("max_safe_temperature_celsius", HARDWARE_LIMITS.get(h.name, 0.0))
        is_safe = res.get("is_safe", h.target_temperature_celsius <= max_t)
        flags.append(HardwareFlag(
            equipment_name=h.name,
            target_temperature_celsius=h.target_temperature_celsius,
            max_safe_temperature_celsius=max_t,
            is_safe=is_safe
        ))

    state.hardware_flags = flags
    unsafe = [f.equipment_name for f in flags if not f.is_safe]
    obs = f"Evaluated {len(flags)} hardware items. Unsafe: {unsafe if unsafe else 'None'}"

    state.add_trace(
        agent="HardwareComplianceAgent",
        action=f"FastMCP Hardware Check ({len(flags)} items)",
        observation=obs,
        duration_ms=int((time.time() - start_time) * 1000),
        status="error" if unsafe else "success"
    )
    return state
