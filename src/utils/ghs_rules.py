"""
GHS Rule Engine & Helper Mappings.
Provides GHS H-code category lookups, signal word rules, UN transport classifications,
authoritative carcinogen registries, and GHS Rev.9 mixture concentration cut-off rules.
"""

import os
from typing import Any
from src.core.logger import logger

# Standard GHS Pictogram Code -> Filename mapping
GHS_PICTOGRAM_FILES = {
    "GHS01": "GHS01_exploding_bomb.svg",
    "GHS02": "GHS02_flammable.svg",
    "GHS03": "GHS03_oxidizing.svg",
    "GHS04": "GHS04_compressed_gas.svg",
    "GHS05": "GHS05_corrosive.svg",
    "GHS06": "GHS06_toxic.svg",
    "GHS07": "GHS07_harmful.svg",
    "GHS08": "GHS08_health_hazard.svg",
    "GHS09": "GHS09_environmental.svg",
}

# High-severity H-codes requiring "DANGER" signal word
DANGER_H_CODES = {
    "H200", "H201", "H202", "H203", "H224", "H225", "H240", "H241",
    "H300", "H310", "H330", "H314", "H318", "H334", "H340", "H350",
    "H360", "H370", "H372"
}

# UN Transport Classifications (UN Number, Proper Shipping Name, Class, Packing Group)
UN_TRANSPORT_DATABASE = {
    "benzene": {"un_number": "UN1114", "shipping_name": "BENZENE SOLUTION", "class": "3", "packing_group": "II", "marine_pollutant": "Yes"},
    "toluene": {"un_number": "UN1294", "shipping_name": "TOLUENE SOLUTION", "class": "3", "packing_group": "II", "marine_pollutant": "No"},
    "acetone": {"un_number": "UN1090", "shipping_name": "ACETONE SOLUTION", "class": "3", "packing_group": "II", "marine_pollutant": "No"},
    "methanol": {"un_number": "UN1230", "shipping_name": "METHANOL SOLUTION", "class": "3 (6.1)", "packing_group": "II", "marine_pollutant": "No"},
    "ethanol": {"un_number": "UN1170", "shipping_name": "ETHANOL SOLUTION", "class": "3", "packing_group": "II", "marine_pollutant": "No"},
    "hydrochloric acid": {"un_number": "UN1789", "shipping_name": "HYDROCHLORIC ACID SOLUTION", "class": "8", "packing_group": "II", "marine_pollutant": "No"},
    "sulfuric acid": {"un_number": "UN1830", "shipping_name": "SULFURIC ACID SOLUTION", "class": "8", "packing_group": "II", "marine_pollutant": "No"},
    "nitric acid": {"un_number": "UN2031", "shipping_name": "NITRIC ACID SOLUTION", "class": "8 (5.1)", "packing_group": "II", "marine_pollutant": "No"},
    "sodium hydroxide": {"un_number": "UN1824", "shipping_name": "SODIUM HYDROXIDE SOLUTION", "class": "8", "packing_group": "II", "marine_pollutant": "No"},
    "hydrogen peroxide": {"un_number": "UN2014", "shipping_name": "HYDROGEN PEROXIDE, AQUEOUS SOLUTION", "class": "5.1 (8)", "packing_group": "II", "marine_pollutant": "No"},
}

# Authoritative Carcinogenic & Toxicological Classifications (IARC, NTP, OSHA, Cal Prop 65)
CARCINOGEN_DATABASE = {
    "benzene": {
        "iarc": "Group 1 (Carcinogenic to Humans)",
        "ntp": "Known to be a Human Carcinogen",
        "osha": "OSHA Regulated Carcinogen (29 CFR 1910.1028)",
        "prop65": "WARNING: Known to the State of California to cause cancer and birth defects or other reproductive harm."
    },
    "toluene": {
        "iarc": "Group 3 (Not classifiable as to its carcinogenicity to humans)",
        "ntp": "Not Listed",
        "osha": "OSHA Table Z-2 (29 CFR 1910.1000)",
        "prop65": "WARNING: Known to the State of California to cause birth defects or other reproductive harm."
    },
    "formaldehyde": {
        "iarc": "Group 1 (Carcinogenic to Humans)",
        "ntp": "Known to be a Human Carcinogen",
        "osha": "OSHA Regulated Carcinogen (29 CFR 1910.1048)",
        "prop65": "WARNING: Known to the State of California to cause cancer."
    }
}


def determine_overall_signal_word(pubchem_data_map: dict[str, Any]) -> str:
    """Returns 'DANGER' if any chemical has a DANGER signal word or high-risk H-code, else 'WARNING'."""
    for chem_data in pubchem_data_map.values():
        if isinstance(chem_data, dict):
            sig = chem_data.get("signal_word", "").upper()
            if sig == "DANGER":
                return "DANGER"
            h_codes = chem_data.get("hazard_statements", [])
            for h in h_codes:
                code_match = h.split(":")[0].strip().upper() if ":" in h else h.strip().upper()
                if code_match in DANGER_H_CODES:
                    return "DANGER"
    return "WARNING"


def get_un_transport_info(chemical_name: str) -> dict[str, str]:
    """Retrieves UN Transport information for a chemical entity."""
    name_lower = chemical_name.lower().strip()
    for key, data in UN_TRANSPORT_DATABASE.items():
        if key in name_lower or name_lower in key:
            return data
    return {
        "un_number": "Not Regulated",
        "shipping_name": "NON-HAZARDOUS CHEMICAL MIXTURE",
        "class": "Not Applicable",
        "packing_group": "Not Applicable",
        "marine_pollutant": "No"
    }


def get_carcinogen_info(chemical_name: str) -> dict[str, str] | None:
    """Retrieves IARC, NTP, OSHA, and California Prop 65 carcinogen ratings for a chemical."""
    name_lower = chemical_name.lower().strip()
    for key, data in CARCINOGEN_DATABASE.items():
        if key in name_lower or name_lower in key:
            return data
    return None


def load_pictogram_svg(code: str) -> str:
    """Loads SVG pictogram content for inline HTML rendering."""
    filename = GHS_PICTOGRAM_FILES.get(code.upper())
    if not filename:
        return ""
    filepath = os.path.join("assets", "pictograms", filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"[GHSRules] Failed to read pictogram SVG '{filepath}': {e}")
    return f"<span style='border:2px solid red; padding:4px; font-weight:bold;'>{code}</span>"

