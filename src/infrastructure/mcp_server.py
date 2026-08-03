import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mcp.server.fastmcp import FastMCP
from src.core.constants import HARDWARE_LIMITS

mcp = FastMCP("lab-hardware-server")


@mcp.tool()
def check_hardware_compatibility(
    equipment_name: str,
    target_temperature_celsius: float
) -> dict:
    key = equipment_name.lower().strip()

    if key not in HARDWARE_LIMITS:
        return {
            "error": f"Unknown equipment: '{equipment_name}'. Cannot verify thermal safety.",
            "known_equipment": list(HARDWARE_LIMITS.keys())
        }

    max_temp = HARDWARE_LIMITS[key]
    is_safe = target_temperature_celsius <= max_temp

    return {
        "equipment_name":               equipment_name,
        "target_temperature_celsius":    target_temperature_celsius,
        "max_safe_temperature_celsius":  max_temp,
        "is_safe":                       is_safe
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
