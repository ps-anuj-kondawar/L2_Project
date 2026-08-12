"""
ChemShield AI — Core Constants.

This module defines all authoritative chemical and hardware safety databases.
These are the single source of truth used by every agent in the pipeline.
Values are sourced from OSHA 29 CFR 1910.1000 Table Z-1/Z-2, specific OSHA standards,
and peer-reviewed chemical safety references. All limits are for US OSHA unless noted.

IMPORTANT: Do NOT change limit values without citing the regulatory reference.
Incorrect limits could cause a false-COMPLIANT verdict for a hazardous chemical.
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION_NAME = "regulatory_data"

RAG_DATA_PATH = "./data/regulatory_framework.txt"
RAG_TOP_K = 5

MCP_SERVER_SCRIPT = "src/infrastructure/mcp_server.py"


# ── Hardware Thermal Limits (Max safe operating temperature in °C) ──────────
# Keys must exactly match the normalized output of fuzzy_match_hardware().
# Source: ASTM standards, manufacturer datasheets, chemical engineering references.
HARDWARE_LIMITS: dict[str, int] = {
    # Glass
    "soda-lime glass":              100,   # Standard lab glass — low thermal resistance
    "soda-lime glass beaker":       100,   # Same as above, alias
    "borosilicate glass":           500,   # Pyrex/Kimax grade borosilicate
    "borosilicate glass beaker":    500,   # Same as above, alias
    "borosilicate glass flask":     500,
    # Plastics
    "polypropylene container":       80,   # PP melts at ~160°C; use temp limit = 80°C
    "polypropylene beaker":          80,
    "polyethylene container":        60,   # HDPE — lower thermal limit
    "ptfe container":               260,   # PTFE / Teflon: excellent thermal resistance
    "teflon container":             260,
    # Metals
    "stainless steel beaker":       600,
    "stainless steel flask":        600,
    "stainless steel reactor":      600,
}


# ── Chemical Boiling Points in Celsius ─────────────────────────────────────
# Used for detecting boiling-point hazards when operating temperature >= boiling point.
# Source: NIST Chemistry WebBook, PubChem Physical Properties.
BOILING_POINTS_CELSIUS: dict[str, float] = {
    "acetone":              56.0,
    "methanol":             65.0,
    "isopropanol":          82.0,
    "ipa":                  82.0,
    "ethanol":              78.0,
    "toluene":             111.0,
    "benzene":              80.1,
    "chloroform":           61.2,   # CRITICAL — very low boiling point
    "dichloromethane":      39.6,   # Also known as methylene chloride; very volatile
    "methylene chloride":   39.6,
    "diethyl ether":        34.6,   # Extreme flammability and low boiling point
    "hexane":               69.0,
    "xylene":              138.0,
    "ethyl acetate":        77.1,
    "formaldehyde":        -19.0,   # Gas at room temperature; listed for completeness
    "ammonia":             -33.3,   # Gas at room temperature
    "acetonitrile":         82.0,
    "thf":                  66.0,   # Tetrahydrofuran
    "tetrahydrofuran":      66.0,
    "dmso":                189.0,   # Dimethyl sulfoxide
    "dimethyl sulfoxide":  189.0,
    "hydrogen peroxide":   150.2,
    "acetic acid":         118.1,
}


# ── Master Chemical Database ─────────────────────────────────────────────────
# Authoritative, hardcoded regulatory limits for all OSHA-regulated chemicals.
# This database is ALWAYS checked BEFORE the SQLite cache to prevent stale data
# from causing a false-COMPLIANT verdict.
#
# Field definitions:
#   pel_ppm         : OSHA Permissible Exposure Limit (8-hr TWA) in ppm air
#   stel_ppm        : OSHA Short-Term Exposure Limit (15-min) in ppm air, or None
#   ceiling_ppm     : OSHA Ceiling value (must not exceed at any time) in ppm, or None
#   action_level_ppm: OSHA Action Level (triggers air monitoring) in ppm, or None
#   liquid_pct_limit: Maximum allowed concentration in liquid formulation (% v/v or w/w), or None
#   pel_mg_m3       : PEL in mg/m3 for chemicals where ppm is not standard, or None
#   cas_number      : CASRN — Chemical Abstracts Service Registry Number
#   standard        : Primary OSHA/regulatory standard (CFR citation)
#   hazard_class    : Primary hazard category for SDS classification purposes
#
# IMPORTANT: pel_ppm and liquid_pct_limit are DIFFERENT physical quantities.
# pel_ppm = airborne concentration limit (worker inhalation safety)
# liquid_pct_limit = formulation concentration limit (mixture composition)
# These must NEVER be compared directly.
MASTER_CHEMICAL_DATABASE: dict[str, dict] = {
    "benzene": {
        "pel_ppm":          1.0,
        "stel_ppm":         5.0,
        "ceiling_ppm":      None,
        "action_level_ppm": 0.5,
        "liquid_pct_limit": 0.1,   # Max 0.1% v/v in open formulation systems
        "pel_mg_m3":        None,
        "cas_number":       "71-43-2",
        "standard":         "29 CFR 1910.1028",
        "hazard_class":     "carcinogen",
    },
    "acetone": {
        "pel_ppm":          1000.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "67-64-1",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "toluene": {
        "pel_ppm":          200.0,
        "stel_ppm":         300.0,  # OSHA Ceiling (not a standard STEL)
        "ceiling_ppm":      300.0,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "108-88-3",
        "standard":         "29 CFR 1910.1000 Table Z-2",
        "hazard_class":     "reproductive_hazard",
    },
    "methanol": {
        "pel_ppm":          200.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "67-56-1",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "toxic",
    },
    "isopropanol": {
        "pel_ppm":          400.0,
        "stel_ppm":         500.0,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "67-63-0",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "ipa": {  # Alias for isopropanol
        "pel_ppm":          400.0,
        "stel_ppm":         500.0,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "67-63-0",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "ethanol": {
        "pel_ppm":          1000.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "64-17-5",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "chloroform": {
        "pel_ppm":          50.0,   # Ceiling value (must not be exceeded)
        "stel_ppm":         None,
        "ceiling_ppm":      50.0,   # This is a ceiling, not TWA
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "67-66-3",
        "standard":         "29 CFR 1910.1000 Table Z-2",
        "hazard_class":     "carcinogen_suspect",
    },
    "xylene": {
        "pel_ppm":          100.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "1330-20-7",  # Mixed isomers
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "irritant",
    },
    "hexane": {
        "pel_ppm":          500.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "110-54-3",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "neurotoxic",
    },
    "formaldehyde": {
        "pel_ppm":          0.75,
        "stel_ppm":         2.0,
        "ceiling_ppm":      None,
        "action_level_ppm": 0.5,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "50-00-0",
        "standard":         "29 CFR 1910.1048",
        "hazard_class":     "carcinogen",
    },
    "ethyl acetate": {
        "pel_ppm":          400.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "141-78-6",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "dichloromethane": {
        "pel_ppm":          25.0,
        "stel_ppm":         125.0,
        "ceiling_ppm":      None,
        "action_level_ppm": 12.5,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "75-09-2",
        "standard":         "29 CFR 1910.1052",
        "hazard_class":     "carcinogen_suspect",
    },
    "methylene chloride": {  # Alias for dichloromethane
        "pel_ppm":          25.0,
        "stel_ppm":         125.0,
        "ceiling_ppm":      None,
        "action_level_ppm": 12.5,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "75-09-2",
        "standard":         "29 CFR 1910.1052",
        "hazard_class":     "carcinogen_suspect",
    },
    "diethyl ether": {
        "pel_ppm":          400.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "60-29-7",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "sodium hydroxide": {
        "pel_ppm":          None,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        2.0,   # PEL is 2 mg/m3 TWA (not ppm)
        "cas_number":       "1310-73-2",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "corrosive",
    },
    "sulfuric acid": {
        "pel_ppm":          None,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        1.0,   # PEL is 1 mg/m3 TWA (not ppm)
        "cas_number":       "7664-93-9",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "corrosive",
    },
    "hydrochloric acid": {
        "pel_ppm":          5.0,
        "stel_ppm":         None,
        "ceiling_ppm":      5.0,   # OSHA Ceiling value
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "7647-01-0",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "corrosive",
    },
    "ammonia": {
        "pel_ppm":          50.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "7664-41-7",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "toxic",
    },
    "hydrogen peroxide": {
        "pel_ppm":          1.0,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "7722-84-1",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "oxidizer",
    },
    "acetonitrile": {
        "pel_ppm":          40.0,
        "stel_ppm":         60.0,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "75-05-8",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "tetrahydrofuran": {
        "pel_ppm":          200.0,
        "stel_ppm":         250.0,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "109-99-9",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "thf": {  # Alias for tetrahydrofuran
        "pel_ppm":          200.0,
        "stel_ppm":         250.0,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "109-99-9",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "flammable",
    },
    "dimethyl sulfoxide": {
        "pel_ppm":          None,  # OSHA has no established PEL for DMSO
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "67-68-5",
        "standard":         "ACGIH TLV: Not established",
        "hazard_class":     "irritant",
    },
    "dmso": {  # Alias for dimethyl sulfoxide
        "pel_ppm":          None,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "67-68-5",
        "standard":         "ACGIH TLV: Not established",
        "hazard_class":     "irritant",
    },
    "acetic acid": {
        "pel_ppm":          10.0,
        "stel_ppm":         15.0,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "64-19-7",
        "standard":         "29 CFR 1910.1000 Table Z-1",
        "hazard_class":     "corrosive",
    },
    "water": {
        "pel_ppm":          None,
        "stel_ppm":         None,
        "ceiling_ppm":      None,
        "action_level_ppm": None,
        "liquid_pct_limit": None,
        "pel_mg_m3":        None,
        "cas_number":       "7732-18-5",
        "standard":         "Not regulated as hazardous",
        "hazard_class":     "non-hazardous",
    },
}


# ── Chemical Physical Properties Reference Database ────────────────────────
# Sourced from NIST Chemistry WebBook and CRC Handbook of Chemistry and Physics.
# Used for calculating mixture boiling range, flash point, and solubility in Section 9.
PHYSICAL_PROPERTIES: dict[str, dict] = {
    "water": {
        "cas": "7732-18-5", "boiling_point_c": 100.0, "flash_point_c": None,
        "density_g_cm3": 1.000, "water_solubility": "Miscible (Solvent)", "vapor_pressure_kpa": 3.17
    },
    "benzene": {
        "cas": "71-43-2", "boiling_point_c": 80.1, "flash_point_c": -11.1,
        "density_g_cm3": 0.876, "water_solubility": "Insoluble / Immiscible (0.18 g/100 mL at 25°C)", "vapor_pressure_kpa": 12.7
    },
    "acetone": {
        "cas": "67-64-1", "boiling_point_c": 56.05, "flash_point_c": -20.0,
        "density_g_cm3": 0.784, "water_solubility": "Fully Miscible", "vapor_pressure_kpa": 30.6
    },
    "methanol": {
        "cas": "67-56-1", "boiling_point_c": 64.7, "flash_point_c": 11.0,
        "density_g_cm3": 0.792, "water_solubility": "Fully Miscible", "vapor_pressure_kpa": 16.9
    },
    "isopropanol": {
        "cas": "67-63-0", "boiling_point_c": 82.6, "flash_point_c": 12.0,
        "density_g_cm3": 0.786, "water_solubility": "Fully Miscible", "vapor_pressure_kpa": 5.8
    },
    "ipa": {
        "cas": "67-63-0", "boiling_point_c": 82.6, "flash_point_c": 12.0,
        "density_g_cm3": 0.786, "water_solubility": "Fully Miscible", "vapor_pressure_kpa": 5.8
    },
    "ethanol": {
        "cas": "64-17-5", "boiling_point_c": 78.37, "flash_point_c": 13.0,
        "density_g_cm3": 0.789, "water_solubility": "Fully Miscible", "vapor_pressure_kpa": 7.9
    },
    "toluene": {
        "cas": "108-88-3", "boiling_point_c": 110.6, "flash_point_c": 4.4,
        "density_g_cm3": 0.867, "water_solubility": "Insoluble / Immiscible (0.052 g/100 mL at 20°C)", "vapor_pressure_kpa": 3.8
    },
    "chloroform": {
        "cas": "67-66-3", "boiling_point_c": 61.2, "flash_point_c": None,  # Non-flammable liquid
        "density_g_cm3": 1.489, "water_solubility": "Slightly Soluble (0.8 g/100 mL at 20°C)", "vapor_pressure_kpa": 21.2
    },
    "xylene": {
        "cas": "1330-20-7", "boiling_point_c": 138.5, "flash_point_c": 27.0,
        "density_g_cm3": 0.864, "water_solubility": "Insoluble / Immiscible", "vapor_pressure_kpa": 0.8
    },
    "hexane": {
        "cas": "110-54-3", "boiling_point_c": 69.0, "flash_point_c": -22.0,
        "density_g_cm3": 0.655, "water_solubility": "Insoluble / Immiscible", "vapor_pressure_kpa": 17.6
    },
    "formaldehyde": {
        "cas": "50-00-0", "boiling_point_c": -19.0, "flash_point_c": 85.0,  # Formalin solution 37%
        "density_g_cm3": 1.09, "water_solubility": "Fully Miscible", "vapor_pressure_kpa": 0.5
    },
    "dichloromethane": {
        "cas": "75-09-2", "boiling_point_c": 39.6, "flash_point_c": None,  # No flash point by standard tag closed cup
        "density_g_cm3": 1.326, "water_solubility": "Slightly Soluble (1.32 g/100 mL at 20°C)", "vapor_pressure_kpa": 58.1
    },
    "methylene chloride": {
        "cas": "75-09-2", "boiling_point_c": 39.6, "flash_point_c": None,
        "density_g_cm3": 1.326, "water_solubility": "Slightly Soluble (1.32 g/100 mL at 20°C)", "vapor_pressure_kpa": 58.1
    },
    "diethyl ether": {
        "cas": "60-29-7", "boiling_point_c": 34.6, "flash_point_c": -45.0,
        "density_g_cm3": 0.713, "water_solubility": "Slightly Soluble (6.9 g/100 mL at 20°C)", "vapor_pressure_kpa": 71.6
    },
}


# ── CAS Number → Chemical Name map ─────────────────────────────────────────
# Used by reflection_agent to validate CAS numbers in SDS Section 3
# when PubChem data is unavailable. Source: NIST, OSHA standards.
CAS_NUMBER_MAP: dict[str, str] = {
    chem_data["cas_number"]: chem_name
    for chem_name, chem_data in MASTER_CHEMICAL_DATABASE.items()
    if chem_data.get("cas_number")
}

# Reverse map: CAS → name (primary entry only, no aliases)
CAS_TO_NAME: dict[str, str] = {
    "7732-18-5": "water",
    "71-43-2":   "benzene",
    "67-64-1":   "acetone",
    "108-88-3":  "toluene",
    "67-56-1":   "methanol",
    "67-63-0":   "isopropanol",
    "64-17-5":   "ethanol",
    "67-66-3":   "chloroform",
    "1330-20-7": "xylene",
    "110-54-3":  "hexane",
    "50-00-0":   "formaldehyde",
    "141-78-6":  "ethyl acetate",
    "75-09-2":   "dichloromethane",
    "60-29-7":   "diethyl ether",
    "1310-73-2": "sodium hydroxide",
    "7664-93-9": "sulfuric acid",
    "7647-01-0": "hydrochloric acid",
    "7664-41-7": "ammonia",
    "7722-84-1": "hydrogen peroxide",
    "75-05-8":   "acetonitrile",
    "109-99-9":  "tetrahydrofuran",
    "67-68-5":   "dimethyl sulfoxide",
    "64-19-7":   "acetic acid",
}
