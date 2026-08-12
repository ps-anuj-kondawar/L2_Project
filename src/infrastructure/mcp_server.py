"""
ChemShield AI — FastMCP Hardware Safety Server.

Exposes the `check_hardware_compatibility` tool over stdio transport.
This server is launched as a subprocess by the HardwareAgent and communicates
via Model Context Protocol (MCP) stdio transport.

The server performs normalized key matching against HARDWARE_LIMITS to handle
minor naming variations (e.g., 'Borosilicate Glass Beaker' -> 'borosilicate glass beaker').
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from fastmcp import FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP
from src.core.constants import HARDWARE_LIMITS

mcp = FastMCP("lab-hardware-server")


def _resolve_equipment_key(equipment_name: str) -> str | None:
    """
    Resolve an equipment name to a canonical HARDWARE_LIMITS key.

    Performs normalized substring matching — the input may contain
    extra words or capitalization variations that still refer to
    a known equipment type.

    Args:
        equipment_name: User-provided or fuzzy-matched equipment name.

    Returns:
        The matching key from HARDWARE_LIMITS, or None if not found.
    """
    name_lower = equipment_name.lower().strip()
    # Exact match (fastest path)
    if name_lower in HARDWARE_LIMITS:
        return name_lower
    # Substring match: check if any known key is contained in the name
    for key in HARDWARE_LIMITS:
        if key in name_lower:
            return key
    # Reverse substring: check if the name is contained in a known key
    for key in HARDWARE_LIMITS:
        if name_lower in key:
            return key
    return None


@mcp.tool()
def check_hardware_compatibility(
    equipment_name: str,
    target_temperature_celsius: float
) -> dict:
    """
    MCP Tool: Check if laboratory equipment is thermally safe for a target temperature.

    Performs normalized key matching to handle naming variations.
    Returns explicit transport-detectable error for unknown equipment
    (the hardware agent handles fallback to web search in this case).

    Args:
        equipment_name: Name of the lab equipment or container.
        target_temperature_celsius: Target operating temperature in Celsius.

    Returns:
        Dict with is_safe boolean and max_safe_temperature_celsius,
        or error dict if equipment is unknown.
    """
    resolved_key = _resolve_equipment_key(equipment_name)

    if resolved_key is None:
        return {
            "error": f"Unknown equipment: '{equipment_name}'. Cannot verify thermal safety.",
            "known_equipment": list(HARDWARE_LIMITS.keys())
        }

    max_temp = HARDWARE_LIMITS[resolved_key]
    is_safe = target_temperature_celsius <= max_temp

    return {
        "equipment_name":               equipment_name,
        "resolved_equipment_key":       resolved_key,
        "target_temperature_celsius":   target_temperature_celsius,
        "max_safe_temperature_celsius": max_temp,
        "is_safe":                      is_safe
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
