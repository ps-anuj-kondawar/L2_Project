"""
GHS Rule Engine & Helper Mappings.

Provides GHS H-code category lookups, signal word rules, UN transport classifications,
authoritative carcinogen registries, and GHS Rev.9 mixture concentration cut-off rules.

All data sourced from:
- GHS Rev.9 (UN Globally Harmonized System of Classification and Labelling of Chemicals)
- UN Recommendations on the Transport of Dangerous Goods (UNRTDG), 21st edition
- IARC Monographs on the Identification of Carcinogenic Hazards to Humans
- NTP 15th Report on Carcinogens (2021)
- California Proposition 65 (OEHHA)
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

# High-severity H-codes that require the "DANGER" signal word under GHS Rev.9
# These correspond to Category 1 or Category 2 classifications for their respective hazard classes.
DANGER_H_CODES = {
    # Explosives
    "H200", "H201", "H202", "H203",
    # Flammables
    "H224", "H225", "H240", "H241",
    # Acute toxicity (oral, dermal, inhalation)
    "H300", "H310", "H330",
    # Serious eye damage
    "H314", "H318",
    # Respiratory sensitization / carcinogenicity / mutagenicity / reproductive
    "H334", "H340", "H350", "H360",
    # Specific target organ toxicity — single exposure, Category 1
    "H370", "H372",
}

# UN Transport Classifications (UN Number, Proper Shipping Name, Class, Packing Group)
# Source: UNRTDG 21st Edition, Dangerous Goods List (Chapter 3.2)
UN_TRANSPORT_DATABASE = {
    "benzene": {
        "un_number": "UN1114", "shipping_name": "BENZENE",
        "class": "3", "packing_group": "II", "marine_pollutant": "Yes"
    },
    "toluene": {
        "un_number": "UN1294", "shipping_name": "TOLUENE",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "acetone": {
        "un_number": "UN1090", "shipping_name": "ACETONE",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "methanol": {
        "un_number": "UN1230", "shipping_name": "METHANOL",
        "class": "3 (6.1)", "packing_group": "II", "marine_pollutant": "No"
    },
    "ethanol": {
        "un_number": "UN1170", "shipping_name": "ETHANOL SOLUTION",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "hydrochloric acid": {
        "un_number": "UN1789", "shipping_name": "HYDROCHLORIC ACID SOLUTION",
        "class": "8", "packing_group": "II", "marine_pollutant": "No"
    },
    "sulfuric acid": {
        "un_number": "UN1830", "shipping_name": "SULFURIC ACID",
        "class": "8", "packing_group": "II", "marine_pollutant": "No"
    },
    "nitric acid": {
        "un_number": "UN2031", "shipping_name": "NITRIC ACID, other than red fuming",
        "class": "8 (5.1)", "packing_group": "II", "marine_pollutant": "No"
    },
    "sodium hydroxide": {
        "un_number": "UN1824", "shipping_name": "SODIUM HYDROXIDE SOLUTION",
        "class": "8", "packing_group": "II", "marine_pollutant": "No"
    },
    "hydrogen peroxide": {
        "un_number": "UN2014", "shipping_name": "HYDROGEN PEROXIDE, AQUEOUS SOLUTION",
        "class": "5.1 (8)", "packing_group": "II", "marine_pollutant": "No"
    },
    "isopropanol": {
        "un_number": "UN1219", "shipping_name": "ISOPROPANOL",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "ipa": {
        "un_number": "UN1219", "shipping_name": "ISOPROPANOL",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "chloroform": {
        "un_number": "UN1888", "shipping_name": "CHLOROFORM",
        "class": "6.1", "packing_group": "III", "marine_pollutant": "No"
    },
    "xylene": {
        "un_number": "UN1307", "shipping_name": "XYLENES",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "hexane": {
        "un_number": "UN1208", "shipping_name": "HEXANES",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "formaldehyde": {
        "un_number": "UN2209", "shipping_name": "FORMALDEHYDE SOLUTION",
        "class": "8 (3)", "packing_group": "III", "marine_pollutant": "No"
    },
    "dichloromethane": {
        "un_number": "UN1593", "shipping_name": "DICHLOROMETHANE",
        "class": "6.1", "packing_group": "III", "marine_pollutant": "No"
    },
    "methylene chloride": {
        "un_number": "UN1593", "shipping_name": "DICHLOROMETHANE",
        "class": "6.1", "packing_group": "III", "marine_pollutant": "No"
    },
    "diethyl ether": {
        "un_number": "UN1155", "shipping_name": "DIETHYL ETHER",
        "class": "3", "packing_group": "I", "marine_pollutant": "No"
    },
    "ethyl acetate": {
        "un_number": "UN1173", "shipping_name": "ETHYL ACETATE",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "acetonitrile": {
        "un_number": "UN1648", "shipping_name": "ACETONITRILE",
        "class": "3 (6.1)", "packing_group": "II", "marine_pollutant": "No"
    },
    "tetrahydrofuran": {
        "un_number": "UN2056", "shipping_name": "TETRAHYDROFURAN",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "thf": {
        "un_number": "UN2056", "shipping_name": "TETRAHYDROFURAN",
        "class": "3", "packing_group": "II", "marine_pollutant": "No"
    },
    "acetic acid": {
        "un_number": "UN2789", "shipping_name": "ACETIC ACID SOLUTION, glacial or with >80%",
        "class": "8 (3)", "packing_group": "II", "marine_pollutant": "No"
    },
}


# Authoritative Carcinogenic & Toxicological Classifications
# Sources:
# - IARC: International Agency for Research on Cancer (IARC Monographs)
# - NTP: National Toxicology Program (15th Report on Carcinogens, 2021)
# - OSHA: Occupational Safety & Health Administration (29 CFR 1910.1003–1016)
# - Prop 65: California Office of Environmental Health Hazard Assessment (OEHHA)
CARCINOGEN_DATABASE = {
    "benzene": {
        "iarc": "Group 1 (Carcinogenic to Humans — causes leukemia)",
        "ntp": "Known to be a Human Carcinogen (15th RoC)",
        "osha": "OSHA Regulated Carcinogen (29 CFR 1910.1028)",
        "prop65": "WARNING: Known to the State of California to cause cancer and birth defects or other reproductive harm.",
    },
    "toluene": {
        "iarc": "Group 3 (Not classifiable as to its carcinogenicity to humans)",
        "ntp": "Not Listed",
        "osha": "OSHA Table Z-2 (29 CFR 1910.1000) — Reproductive hazard",
        "prop65": "WARNING: Known to the State of California to cause birth defects or other reproductive harm.",
    },
    "formaldehyde": {
        "iarc": "Group 1 (Carcinogenic to Humans — causes nasopharyngeal cancer and leukemia)",
        "ntp": "Known to be a Human Carcinogen (15th RoC)",
        "osha": "OSHA Regulated Carcinogen (29 CFR 1910.1048)",
        "prop65": "WARNING: Known to the State of California to cause cancer.",
    },
    "chloroform": {
        "iarc": "Group 2A (Probably Carcinogenic to Humans)",
        "ntp": "Reasonably Anticipated to be a Human Carcinogen (15th RoC)",
        "osha": "Not listed as OSHA carcinogen; regulated under Table Z-2 (PEL: 50 ppm ceiling)",
        "prop65": "WARNING: Known to the State of California to cause cancer.",
    },
    "dichloromethane": {
        "iarc": "Group 2A (Probably Carcinogenic to Humans)",
        "ntp": "Reasonably Anticipated to be a Human Carcinogen (15th RoC)",
        "osha": "OSHA Regulated Carcinogen (29 CFR 1910.1052)",
        "prop65": "WARNING: Known to the State of California to cause cancer.",
    },
    "methylene chloride": {
        "iarc": "Group 2A (Probably Carcinogenic to Humans)",
        "ntp": "Reasonably Anticipated to be a Human Carcinogen (15th RoC)",
        "osha": "OSHA Regulated Carcinogen (29 CFR 1910.1052)",
        "prop65": "WARNING: Known to the State of California to cause cancer.",
    },
    "xylene": {
        "iarc": "Group 3 (Not classifiable as to its carcinogenicity to humans)",
        "ntp": "Not Listed",
        "osha": "Not classified as OSHA carcinogen; Table Z-1 (PEL: 100 ppm TWA)",
        "prop65": None,
    },
    "hexane": {
        "iarc": "Not classified",
        "ntp": "Not Listed (metabolite 2,5-hexanedione listed as reproductive hazard)",
        "osha": "Not classified as OSHA carcinogen; neurotoxic — peripheral neuropathy risk",
        "prop65": None,
    },
    "sulfuric acid": {
        "iarc": "Group 1 (Carcinogenic to Humans — acid mist classified as carcinogenic)",
        "ntp": "Known to be a Human Carcinogen (acid mist) (15th RoC)",
        "osha": "Occupational carcinogen (acid mist exposure); regulated under 29 CFR 1910.1000 Table Z-1",
        "prop65": "WARNING: Known to the State of California to cause cancer (as acid mist).",
    },
    "hydrogen peroxide": {
        "iarc": "Group 3 (Not classifiable as to its carcinogenicity to humans — animal evidence only)",
        "ntp": "Not Listed",
        "osha": "Not classified as OSHA carcinogen; strong oxidizer",
        "prop65": None,
    },
}


def determine_overall_signal_word(pubchem_data_map: dict[str, Any]) -> str:
    """
    Determine the GHS signal word for a mixture based on individual chemical GHS data.

    Returns 'DANGER' if any chemical has a 'DANGER' signal word or a high-severity
    H-code (Category 1/2 hazard). Returns 'WARNING' otherwise.

    Args:
        pubchem_data_map: Dict mapping chemical name -> PubChem GHS data dict.
                          Each value may contain 'signal_word' and 'hazard_statements'.

    Returns:
        'DANGER' or 'WARNING' (never None or raises).
    """
    for chem_data in pubchem_data_map.values():
        if not isinstance(chem_data, dict):
            continue
        # Guard against None signal_word (BUG-1 fix)
        sig = (chem_data.get("signal_word") or "").upper()
        if sig == "DANGER":
            return "DANGER"
        h_codes = chem_data.get("hazard_statements") or []
        for h in h_codes:
            if not h:
                continue
            code_match = h.split(":")[0].strip().upper() if ":" in h else h.strip().upper()
            if code_match in DANGER_H_CODES:
                return "DANGER"
    return "WARNING"


def get_un_transport_info(chemical_name: str) -> dict[str, str]:
    """
    Retrieve UN Transport classification for a chemical.

    Performs a substring match (both directions) against the UN database keys.
    Returns a 'Not Regulated' sentinel dict if no match is found.

    Args:
        chemical_name: Common name of the chemical (case-insensitive).

    Returns:
        Dict with keys: un_number, shipping_name, class, packing_group, marine_pollutant.
    """
    name_lower = chemical_name.lower().strip()
    for key, data in UN_TRANSPORT_DATABASE.items():
        if key in name_lower or name_lower in key:
            return data
    return {
        "un_number": "Not Regulated",
        "shipping_name": "NON-HAZARDOUS CHEMICAL MIXTURE",
        "class": "Not Applicable",
        "packing_group": "Not Applicable",
        "marine_pollutant": "No",
    }


def get_mixture_un_transport_info(chemicals: list[str]) -> dict[str, str]:
    """
    Determine UN Transport Classification for multi-component liquid mixtures
    under UNRTDG / 49 CFR dangerous goods regulations.

    Multi-component solvent mixtures cannot simply take the single UN number of
    one component. For multi-solvent formulations containing flammables and toxics:
    - Flammable + Toxic (e.g. Acetone + Methanol + Benzene): UN1992 FLAMMABLE LIQUID, TOXIC, N.O.S.
    - Flammable liquid mixture: UN1993 FLAMMABLE LIQUID, N.O.S.
    """
    chems_lower = [c.lower().strip() for c in chemicals if c.lower().strip() != "water"]
    if not chems_lower:
        return {
            "un_number": "Not Regulated",
            "shipping_name": "NON-HAZARDOUS AQUEOUS MIXTURE",
            "class": "Not Applicable",
            "packing_group": "Not Applicable",
            "marine_pollutant": "No",
        }

    flammable_chems = {"acetone", "benzene", "methanol", "ethanol", "isopropanol", "ipa", "toluene", "xylene", "hexane", "ethyl acetate", "diethyl ether", "tetrahydrofuran"}
    toxic_chems = {"methanol", "benzene", "chloroform", "dichloromethane", "formaldehyde", "acetonitrile"}

    has_flammable = any(c in flammable_chems for c in chems_lower)
    has_toxic = any(c in toxic_chems for c in chems_lower)
    has_marine = "benzene" in chems_lower

    if len(chems_lower) > 1 and has_flammable:
        display_names = ", ".join([c.title() for c in chems_lower[:3]])
        if has_toxic:
            return {
                "un_number": "UN1992",
                "shipping_name": f"FLAMMABLE LIQUID, TOXIC, N.O.S. (contains {display_names})",
                "class": "3 (6.1)",
                "packing_group": "II",
                "marine_pollutant": "Yes" if has_marine else "No"
            }
        else:
            return {
                "un_number": "UN1993",
                "shipping_name": f"FLAMMABLE LIQUID, N.O.S. (contains {display_names})",
                "class": "3",
                "packing_group": "II",
                "marine_pollutant": "Yes" if has_marine else "No"
            }

    return get_un_transport_info(chems_lower[0])


def get_carcinogen_info(chemical_name: str) -> dict[str, str] | None:
    """
    Retrieve IARC, NTP, OSHA, and California Prop 65 carcinogen ratings.

    Args:
        chemical_name: Common name of the chemical (case-insensitive).

    Returns:
        Dict with keys: iarc, ntp, osha, prop65 — or None if not in database.
    """
    name_lower = chemical_name.lower().strip()
    for key, data in CARCINOGEN_DATABASE.items():
        if key in name_lower or name_lower in key:
            return data
    return None


def load_pictogram_svg(code: str) -> str:
    """
    Load SVG pictogram file content for inline HTML rendering in the SDS document.

    Args:
        code: GHS pictogram code (e.g., 'GHS02').

    Returns:
        SVG file content as string, or fallback red-border span if file missing,
        or empty string if code is not recognized.
    """
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
