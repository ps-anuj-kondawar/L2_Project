"""
ChemShield AI — Input Validation & Normalization Utilities.

Provides fuzzy name matching, physical boundary checks, and input sanitization
for chemical and hardware entities extracted from unstructured lab notes.

Fuzzy matching uses RapidFuzz WRatio scorer (Levenshtein distance + partial ratio),
which handles common typos like 'benzen' -> 'Benzene' and abbreviation variants
like 'IPA' -> 'Isopropanol'.

Thresholds:
- Chemical correction threshold: 70/100 (conservative — avoids false corrections)
- Hardware matching threshold:   70/100 (same rationale)
- Physical boundary warning:     150% of hardware rated limit (clearly implausible only)
"""

from rapidfuzz import process, fuzz
from src.core.constants import BOILING_POINTS_CELSIUS, HARDWARE_LIMITS, MASTER_CHEMICAL_DATABASE

# Master list of verified chemical names aligned with MASTER_CHEMICAL_DATABASE and RAG chunks.
# Used by the Copilot to detect chemicals mentioned in chat messages.
KNOWN_CHEMICALS = [
    "Benzene", "Toluene", "Acetone", "Methanol", "Ethanol",
    "Isopropanol", "IPA", "Water", "Chloroform", "Xylene",
    "Hexane", "Diethyl Ether", "Ethyl Acetate", "Dichloromethane",
    "Methylene Chloride", "Formaldehyde", "Ammonia", "Hydrogen Peroxide",
    "Acetonitrile", "Tetrahydrofuran", "THF", "DMSO", "Dimethyl Sulfoxide",
    "Acetic Acid", "Sodium Hydroxide", "Sulfuric Acid", "Hydrochloric Acid",
]


def fuzzy_match_chemical(name: str) -> tuple[str, float]:
    """
    Fuzzy-match a chemical name string against the KNOWN_CHEMICALS list.

    Used to correct typos and abbreviations in user input before processing
    (e.g., 'benzen' -> 'Benzene', score 87; 'IPA' -> 'Isopropanol', score 90).

    Args:
        name: Raw chemical name from entity extraction.

    Returns:
        Tuple of (best_matched_name, confidence_score_0_to_100).
        Returns (name, 0.0) if name is too short to match reliably.
    """
    if len(name.strip()) < 3:
        return name, 0.0
    result = process.extractOne(name, KNOWN_CHEMICALS, scorer=fuzz.WRatio)
    if result:
        return result[0], result[1]
    return name, 0.0


def validate_and_correct_chemicals(
    chemicals: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Validate and fuzzy-correct chemical names against the known chemical list.

    Applies correction only when:
    - The fuzzy match confidence is >= 70/100 (to avoid false corrections)
    - The matched name is different from the input (avoid no-op corrections)

    Correction messages are returned separately so the Supervisor can include
    them in the compliance report as 'auto-correction' notes visible to the user.

    Args:
        chemicals: List of (name, concentration) tuples from entity extraction.

    Returns:
        Tuple of (corrected_list, correction_messages).
    """
    corrected: list[tuple[str, str]] = []
    messages:  list[str] = []

    for name, conc in chemicals:
        match, score = fuzzy_match_chemical(name)
        if score >= 70 and match.lower() != name.lower():
            messages.append(
                f"'{name}' was interpreted as '{match}' (match score: {score:.0f}/100). "
                f"Please verify your input."
            )
            corrected.append((match, conc))
        else:
            corrected.append((name, conc))

    return corrected, messages


def validate_physical_boundaries(
    chemicals: list[tuple[str, str]],
    hardware: list[tuple[str, float]],
) -> list[str]:
    """
    Detect physically implausible or unit-inconsistent values in the formulation.

    Checks performed:
    1. Concentration in ppm for a formulation % context — ppm is an airborne unit
       and cannot directly represent a liquid formulation percentage.
    2. Hardware temperature far above the material's rated limit (>150%) —
       physically implausible and likely a user input error.

    These warnings do NOT block the audit (they are advisory), but are included
    in the compliance report boundary_warnings field so the user is informed.

    Args:
        chemicals: List of (name, concentration_str) tuples.
        hardware: List of (equipment_name, target_temperature_celsius) tuples.

    Returns:
        List of warning message strings. Empty list if no issues detected.
    """
    warnings: list[str] = []

    for name, conc in chemicals:
        # Detect airborne units (ppm) specified as formulation concentration
        if conc and "ppm" in conc.lower():
            warnings.append(
                f"'{name}': specified concentration '{conc}' uses airborne exposure units (ppm). "
                f"GHS Section 3 composition requires weight/volume percentage (% w/w or % v/v). "
                f"Note: ppm airborne limits and formulation % are different quantities."
            )

    for hw_name, temp in hardware:
        hw_limit = HARDWARE_LIMITS.get(hw_name.lower(), 0)
        if hw_limit and temp is not None and temp > hw_limit * 1.5:
            warnings.append(
                f"'{hw_name}': {temp}°C is far above its rated max of {hw_limit}°C — "
                f"physically implausible, please check your input."
            )

    return warnings


def fuzzy_match_hardware(name: str) -> str:
    """
    Fuzzy-match a hardware/equipment name against known HARDWARE_LIMITS keys.

    Normalizes equipment naming variations to canonical keys used by the MCP server.
    For example: 'Pyrex glass beaker' -> 'borosilicate glass beaker' (score 78).

    Args:
        name: Raw equipment name from entity extraction.

    Returns:
        The closest matching canonical hardware key if confidence >= 70/100,
        otherwise the original name unchanged.
    """
    known = list(HARDWARE_LIMITS.keys())
    result = process.extractOne(name, known, scorer=fuzz.WRatio)
    if result and result[1] >= 70:
        return result[0]
    return name
