import re
from rapidfuzz import process, fuzz
from src.core.constants import BOILING_POINTS_CELSIUS, HARDWARE_LIMITS

# Master list of verified chemical names — pulled from ChromaDB metadata + known constants
KNOWN_CHEMICALS = [
    "Benzene", "Toluene", "Acetone", "Methanol", "Ethanol",
    "Isopropanol", "IPA", "Water", "Chloroform", "Xylene",
    "Hexane", "Diethyl Ether", "Formaldehyde", "Ammonia",
]


def fuzzy_match_chemical(name: str) -> tuple[str, float]:
    """Return (best_match_name, confidence_score_0_to_100)."""
    result = process.extractOne(name, KNOWN_CHEMICALS, scorer=fuzz.WRatio)
    if result:
        return result[0], result[1]
    return name, 0.0


def validate_and_correct_chemicals(
    chemicals: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Check each chemical name against the known list via fuzzy matching.
    Returns (corrected_list, correction_messages).
    Threshold: if confidence >= 70 and name differs, apply correction.
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
    """Return warnings for physically impossible or inconsistent values."""
    warnings: list[str] = []

    for name, conc in chemicals:
        # Detect contradictory unit (e.g. "5% ppm")
        if conc and "%" in conc and "ppm" in conc.lower():
            warnings.append(
                f"'{name}': concentration '{conc}' contains contradictory units (% and ppm). "
                f"Please clarify which unit applies."
            )

    for hw_name, temp in hardware:
        # Temperature above hardware melting/failure threshold (with 50% safety margin)
        hw_limit = HARDWARE_LIMITS.get(hw_name.lower(), 0)
        if hw_limit and temp > hw_limit * 1.5:
            warnings.append(
                f"'{hw_name}': {temp}°C is far above its rated max of {hw_limit}°C — "
                f"physically implausible, please check your input."
            )

    return warnings


def fuzzy_match_hardware(name: str) -> str:
    """Fuzzy match hardware name against KNOWN_HARDWARE. Returns matched key or original."""
    known = list(HARDWARE_LIMITS.keys())
    result = process.extractOne(name, known, scorer=fuzz.WRatio)
    if result and result[1] >= 70:
        return result[0]
    return name
