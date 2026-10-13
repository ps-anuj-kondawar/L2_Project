"""
ChemShield AI — PubChem Intelligence & PUG-REST Client.

Provides asynchronous HTTP client interfaces to the National Center for
Biotechnology Information (NCBI) PubChem API services:
- PUG-REST Compound Lookup: Resolves chemical names to PubChem Compound IDs (CIDs)
- Registry ID Cross-References: Extracts authoritative CAS Registry Numbers
- Computed Physical Properties: Fetches MolecularWeight, BoilingPoint, FlashPoint, Density
- PUG-View GHS Annotations: Retrieves Globally Harmonized System classifications,
  hazard codes (H-codes), precautionary statements (P-codes), signal words, and pictograms.

Performance & Reliability:
- Global rate-limiting semaphore (max 5 concurrent requests) prevents NCBI HTTP 429 throttling
- 7-day SQLite local caching layer for instant repeat lookups
"""

import asyncio
import re
import urllib.parse
from typing import Any

import httpx

from src.core.logger import logger
from src.core.models import PubChemData
from src.infrastructure.cache import get_pubchem_cache, set_pubchem_cache

# Compiled regex patterns
_H_CODE_PATTERN = re.compile(r"H\d{3}")
_P_CODE_PATTERN = re.compile(r"P\d{3}")
_H_TEXT_PATTERN = re.compile(r"H\d{3}:?\s*[^\"'\n,]+")
_P_TEXT_PATTERN = re.compile(r"P\d{3}:?\s*[^\"'\n,]+")
_CAS_PATTERN = re.compile(r"\b\d{2,7}-\d{2}-\d\b")

# Rate limit semaphore lazy-initialized on first use inside the running event loop
_pubchem_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Return the global concurrency-limiting semaphore for PubChem requests."""
    global _pubchem_semaphore
    if _pubchem_semaphore is None:
        _pubchem_semaphore = asyncio.Semaphore(5)
    return _pubchem_semaphore


async def _fetch_json(url: str, timeout: float = 10.0) -> dict | None:
    """
    Execute rate-limited asynchronous HTTP GET request and parse JSON response.

    Args:
        url (str): Target REST URL.
        timeout (float): Request timeout in seconds. Defaults to 10.0.

    Returns:
        dict | None: Parsed JSON payload or None on network/HTTP error.
    """
    async with _get_semaphore():
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, timeout=timeout)
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.warning(f"PubChem API fetch error for URL {url}: {e}")
    return None


async def get_pubchem_cid(chemical_name: str) -> int | None:
    """
    Query PubChem PUG REST API to resolve a chemical name to its primary Compound ID (CID).

    Args:
        chemical_name (str): Raw chemical name or synonym.

    Returns:
        int | None: PubChem CID integer if found; None otherwise.
    """
    encoded_name = urllib.parse.quote(chemical_name.strip())
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{encoded_name}/cids/JSON"
    data = await _fetch_json(url)
    if data and "IdentifierList" in data and "CID" in data["IdentifierList"]:
        return data["IdentifierList"]["CID"][0]
    return None


async def get_pubchem_cas(cid: int) -> str | None:
    """
    Query PubChem RegistryID xref endpoint to retrieve the verified CAS number for a CID.

    Args:
        cid (int): PubChem Compound ID.

    Returns:
        str | None: Formatted CAS Registry Number string (e.g. '71-43-2') or None.
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/xrefs/RegistryID/JSON"
    data = await _fetch_json(url)
    if data and "InformationList" in data and "Information" in data["InformationList"]:
        for info in data["InformationList"]["Information"]:
            for reg_id in info.get("RegistryID", []):
                if re.match(r"^\d{2,7}-\d{2}-\d$", reg_id):
                    return reg_id
    return None


async def get_pubchem_properties(cid: int) -> dict[str, float | None]:
    """
    Retrieve experimental and computed physical constants for a CID.

    Args:
        cid (int): PubChem Compound ID.

    Returns:
        dict[str, float | None]: Dictionary with molecular_weight, boiling_point_celsius,
                                  flash_point_celsius, and density.
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularWeight,BoilingPoint,FlashPoint,Density/JSON"
    data = await _fetch_json(url)
    props: dict[str, float | None] = {
        "molecular_weight": None,
        "boiling_point_celsius": None,
        "flash_point_celsius": None,
        "density": None,
    }
    if data and "PropertyTable" in data and "Properties" in data["PropertyTable"]:
        p = data["PropertyTable"]["Properties"][0]
        if "MolecularWeight" in p:
            try:
                props["molecular_weight"] = float(p["MolecularWeight"])
            except (ValueError, TypeError):
                pass
        if "BoilingPoint" in p:
            try:
                m = re.search(r"(-?\d+(?:\.\d+)?)", str(p["BoilingPoint"]))
                if m:
                    props["boiling_point_celsius"] = float(m.group(1))
            except (ValueError, TypeError):
                pass
    return props


def _walk_sections(sections: list, target_heading: str) -> list:
    """
    Recursively search PubChem section trees for headings matching target_heading.

    Args:
        sections (list): List of section nodes from PubChem PUG-View JSON.
        target_heading (str): Heading label substring to match.

    Returns:
        list: Matching section dictionary nodes.
    """
    found = []
    for sec in sections:
        if target_heading.lower() in sec.get("TOCHeading", "").lower():
            found.append(sec)
        for sub in sec.get("Section", []):
            found.extend(_walk_sections([sub], target_heading))
    return found


def _extract_string_values(section: dict) -> list[str]:
    """
    Extract all StringWithMarkup text values from a PubChem Information block.

    Args:
        section (dict): PubChem section dictionary node.

    Returns:
        list[str]: Flattened list of extracted string values.
    """
    values = []
    for info in section.get("Information", []):
        for val in info.get("Value", {}).get("StringWithMarkup", []):
            s = val.get("String", "")
            if s:
                values.append(s)
    return values


async def get_pubchem_ghs(cid: int) -> dict[str, Any]:
    """
    Query PubChem PUG-View endpoint for GHS classification annotations.

    Extracts signal words, pictograms (GHS01-GHS09), H-statements, and P-statements.

    Args:
        cid (int): PubChem Compound ID.

    Returns:
        dict[str, Any]: Dictionary containing signal_word, ghs_pictogram_codes,
                        hazard_statements, and precautionary_statements.
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=GHS+Classification"
    data = await _fetch_json(url)
    ghs_info: dict[str, Any] = {
        "signal_word": "WARNING",
        "ghs_pictogram_codes": [],
        "hazard_statements": [],
        "precautionary_statements": [],
    }
    if not data:
        return ghs_info

    try:
        top_sections = data.get("Record", {}).get("Section", [])
        ghs_sections = _walk_sections(top_sections, "GHS Classification")
        if not ghs_sections and "Record" in data:
            ghs_sections = [data["Record"]]

        for ghs_sec in ghs_sections:
            for sub in ghs_sec.get("Section", []):
                heading = sub.get("TOCHeading", "")
                values = _extract_string_values(sub)
                if "Signal" in heading:
                    for v in values:
                        if "DANGER" in v.upper():
                            ghs_info["signal_word"] = "DANGER"
                elif "Pictogram" in heading:
                    for v in values:
                        for code in ["GHS01", "GHS02", "GHS03", "GHS04", "GHS05", "GHS06", "GHS07", "GHS08", "GHS09"]:
                            if code in v and code not in ghs_info["ghs_pictogram_codes"]:
                                ghs_info["ghs_pictogram_codes"].append(code)
                elif "Hazard" in heading:
                    for v in values:
                        if _H_CODE_PATTERN.search(v) and v not in ghs_info["hazard_statements"]:
                            ghs_info["hazard_statements"].append(v)
                elif "Precautionary" in heading:
                    for v in values:
                        if _P_CODE_PATTERN.search(v) and v not in ghs_info["precautionary_statements"]:
                            ghs_info["precautionary_statements"].append(v)

        # Fallback to text_nodes regex if section walker found nothing specific
        if not ghs_info["ghs_pictogram_codes"] and not ghs_info["hazard_statements"]:
            text_nodes = str(data)
            if "DANGER" in text_nodes.upper():
                ghs_info["signal_word"] = "DANGER"
            for code in ["GHS01", "GHS02", "GHS03", "GHS04", "GHS05", "GHS06", "GHS07", "GHS08", "GHS09"]:
                if code in text_nodes and code not in ghs_info["ghs_pictogram_codes"]:
                    ghs_info["ghs_pictogram_codes"].append(code)
            h_codes = list(set(_H_TEXT_PATTERN.findall(text_nodes)))
            ghs_info["hazard_statements"] = h_codes[:8]
            p_codes = list(set(_P_TEXT_PATTERN.findall(text_nodes)))
            ghs_info["precautionary_statements"] = p_codes[:10]

    except Exception as e:
        logger.warning(f"Error parsing PubChem GHS classification for CID {cid}: {e}")

    return ghs_info


async def get_pubchem_data(chemical_name: str) -> PubChemData:
    """
    Retrieve aggregated PubChem intelligence for a given chemical name.

    Orchestrates cache verification, CID resolution, and concurrent async queries
    for CAS registry numbers, physical properties, and GHS classification blocks.

    Args:
        chemical_name (str): Chemical name or common synonym.

    Returns:
        PubChemData: Fully populated domain model.
    """
    norm_name = chemical_name.strip().lower()

    # Step 1: L2 SQLite Cache Check (Instant repeat lookup, avoids external API costs)
    cached = get_pubchem_cache(norm_name)
    if cached:
        logger.info(f"PubChem SQLite Cache HIT for '{chemical_name}'.")
        return PubChemData.model_validate(cached)

    logger.info(f"PubChem API Lookup for '{chemical_name}'...")
    # Step 2: Resolve Chemical Name to PubChem Compound ID (CID)
    cid = await get_pubchem_cid(chemical_name)
    if not cid:
        logger.warning(f"PubChem CID MISS for '{chemical_name}'. Returning default PubChemData.")
        res = PubChemData(
            chemical_name=chemical_name,
            source="PubChem (Not Found - Fallback to RAG)"
        )
        set_pubchem_cache(norm_name, res.model_dump())
        return res

    # Step 3: Concurrent Fetch of CAS, Physical Properties, and GHS Classifications
    # Uses asyncio.gather with rate-limiting semaphore for maximum throughput
    cas, props, ghs = await asyncio.gather(
        get_pubchem_cas(cid),
        get_pubchem_properties(cid),
        get_pubchem_ghs(cid)
    )

    # Step 4: Assemble Validated PubChemData Domain Object
    res = PubChemData(
        chemical_name=chemical_name,
        cid=cid,
        cas_number=cas or "Data not available",
        molecular_weight=props.get("molecular_weight"),
        boiling_point_celsius=props.get("boiling_point_celsius"),
        flash_point_celsius=props.get("flash_point_celsius"),
        density=props.get("density"),
        signal_word=ghs.get("signal_word", "WARNING"),
        ghs_pictogram_codes=ghs.get("ghs_pictogram_codes", []),
        hazard_statements=ghs.get("hazard_statements", []),
        precautionary_statements=ghs.get("precautionary_statements", []),
        source=f"PubChem CID {cid}"
    )

    # Step 5: Persist to SQLite Cache for Subsequent Agent Turns
    set_pubchem_cache(norm_name, res.model_dump())
    return res
