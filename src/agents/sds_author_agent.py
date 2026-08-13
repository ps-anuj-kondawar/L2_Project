import time
import json
import datetime
import re
from jinja2 import Template
from src.core.state import AgentState
from src.core.models import SDSDocument, SDSSection
from src.infrastructure.llm_client import chat as llm_chat
from src.utils.ghs_rules import (
    determine_overall_signal_word,
    load_pictogram_svg,
    get_mixture_un_transport_info,
    get_carcinogen_info,
)
from src.core.constants import (
    MASTER_CHEMICAL_DATABASE,
    CAS_TO_NAME,
    PHYSICAL_PROPERTIES,
    BOILING_POINTS_CELSIUS,
)
from src.core.logger import logger

SDS_SECTION_TITLES = [
    (1, "Identification"),
    (2, "Hazard(s) Identification"),
    (3, "Composition / Information on Ingredients"),
    (4, "First-Aid Measures"),
    (5, "Fire-Fighting Measures"),
    (6, "Accidental Release Measures"),
    (7, "Handling and Storage"),
    (8, "Exposure Controls / Personal Protection"),
    (9, "Physical and Chemical Properties"),
    (10, "Stability and Reactivity"),
    (11, "Toxicological Information"),
    (12, "Ecological Information"),
    (13, "Disposal Considerations"),
    (14, "Transport Information"),
    (15, "Regulatory Information"),
    (16, "Other Information"),
]


def _clean_section_title(sec_num: int, raw_title: str) -> str:
    """Strip leading redundant prefixes like '1.', 'SECTION 1:', '1 -' from section title."""
    cleaned = re.sub(r'^(?:SECTION\s*\d+[\s:-]*)?(?:\d+[\s.:-]*)?', '', raw_title, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else raw_title


def _build_physical_props_str(chem_names: list[str]) -> str:
    """
    Build a physical properties summary string from PHYSICAL_PROPERTIES for the
    actual chemicals in the formulation — no hardcoded chemical names.

    Returns a formatted string with boiling range, flash point, vapor pressure,
    density, and solubility data derived dynamically from PHYSICAL_PROPERTIES.
    """
    bps = []
    fps = []
    vapor_pressures = []
    densities = []
    solubility_parts = []

    for c_name in chem_names:
        c_low = c_name.lower().strip()
        p = PHYSICAL_PROPERTIES.get(c_low, {})
        if p.get("boiling_point_c") is not None:
            bps.append((c_name.title(), p["boiling_point_c"]))
        if p.get("flash_point_c") is not None:
            fps.append((c_name.title(), p["flash_point_c"]))
        if p.get("vapor_pressure_kpa") is not None:
            vapor_pressures.append(f"{c_name.title()}: {p['vapor_pressure_kpa']} kPa at 20°C")
        if p.get("density_g_cm3") is not None:
            densities.append(p["density_g_cm3"])
        if p.get("water_solubility"):
            solubility_parts.append(f"{c_name.title()}: {p['water_solubility']}")

    if bps:
        min_bp = min(v for _, v in bps)
        max_bp = max(v for _, v in bps)
        bp_range = f"{min_bp}°C – {max_bp}°C" if min_bp != max_bp else f"{min_bp}°C"
        bp_detail = "; ".join(f"{n} {v}°C" for n, v in sorted(bps, key=lambda x: x[1]))
        bp_str = f"Initial Boiling Point & Range: {bp_range} ({bp_detail})"
    else:
        bp_str = "Boiling Point: Not available in local database — consult PubChem or SDS"

    if fps:
        min_fp_name, min_fp_val = min(fps, key=lambda x: x[1])
        fp_str = f"Flash Point: {min_fp_val}°C (Lowest in mixture — {min_fp_name})"
    else:
        fp_str = "Flash Point: Not applicable or not available for all components"

    avg_density = round(sum(densities) / len(densities), 3) if densities else None
    density_str = f"Relative Density: ~{avg_density} g/cm³ at 20°C" if avg_density else "Relative Density: Not available"

    vp_str = "Vapor Pressure: " + "; ".join(vapor_pressures) if vapor_pressures else "Vapor Pressure: Not available"
    sol_str = "Water Solubility: " + "; ".join(solubility_parts) if solubility_parts else "Water Solubility: Refer to individual component SDS"

    return "; ".join([bp_str, fp_str, density_str, vp_str, sol_str])


def _build_exposure_limits_str(chem_names: list[str]) -> str:
    """
    Build an exposure limits string for Section 8 from MASTER_CHEMICAL_DATABASE
    for only the actual chemicals in the formulation.
    """
    lines = []
    for c_name in chem_names:
        c_low = c_name.lower().strip()
        if c_low == "water":
            continue
        entry = MASTER_CHEMICAL_DATABASE.get(c_low)
        if entry:
            pel = entry.get("pel_ppm")
            stel = entry.get("stel_ppm")
            ceiling = entry.get("ceiling_ppm")
            mg_m3 = entry.get("pel_mg_m3")
            standard = entry.get("standard", "29 CFR 1910.1000")
            if pel is not None:
                limit_str = f"OSHA PEL: {pel} ppm TWA"
                if stel:
                    limit_str += f", STEL: {stel} ppm"
                if ceiling:
                    limit_str += f", Ceiling: {ceiling} ppm"
            elif mg_m3 is not None:
                limit_str = f"OSHA PEL: {mg_m3} mg/m³"
            else:
                limit_str = "OSHA PEL: Not established"
            lines.append(f"{c_name.title()}: {limit_str} ({standard})")

    return "; ".join(lines) if lines else "No regulated components — see individual component safety data sheets"


def _build_thermal_warnings(chem_names: list[str], hardware: list) -> str:
    """
    Build storage/handling thermal warnings from actual formulation data.
    No hardcoded chemical-specific temperature thresholds.
    """
    warnings = []
    for h in hardware:
        if h.target_temperature_celsius is not None:
            target_t = h.target_temperature_celsius
            for c_name in chem_names:
                c_low = c_name.lower().strip()
                bp = BOILING_POINTS_CELSIUS.get(c_low)
                if bp is None:
                    p = PHYSICAL_PROPERTIES.get(c_low, {})
                    bp = p.get("boiling_point_c")
                if bp is not None and target_t >= bp:
                    warnings.append(
                        f"CRITICAL THERMAL HAZARD: Operating temperature {target_t}°C "
                        f"EXCEEDS the boiling point of {c_name.title()} ({bp}°C). "
                        f"Storing or heating at {target_t}°C creates severe vapor pressure, "
                        f"container overpressurization, and explosion risk. "
                        f"DO NOT heat/store {c_name.title()} above {bp - 10:.0f}°C. "
                        f"Use explosion-proof storage at ambient temperature (15–25°C)."
                    )
    if warnings:
        return "\n".join(warnings)
    return "Store at ambient room temperature (15–25°C) in a cool, dry, well-ventilated area away from heat, sparks, and ignition sources."


async def run_sds_author_agent(state: AgentState) -> AgentState:
    """
    GHS SDS Authoring Agent.
    Synthesizes formulation information and PubChem data into a complete 16-section SDS HTML document.
    All section content is derived dynamically from the actual formulation — no hardcoded chemical names.
    """
    start_time = time.time()
    logger.info("[SDSAuthorAgent] Generating 16-Section GHS Safety Data Sheet...")

    # Determine product name
    if state.chemicals:
        chem_names = [c.name for c in state.chemicals]
        product_name = "Formulation: " + " + ".join(chem_names)
    else:
        chem_names = []
        product_name = state.user_input[:40]

    # Collect pictograms and signal word from actual PubChem data
    all_pictograms = set()
    for p_data in state.pubchem_data.values():
        if isinstance(p_data, dict):
            for pic in p_data.get("ghs_pictogram_codes", []):
                all_pictograms.add(pic)

    if not all_pictograms:
        all_pictograms.add("GHS07")

    signal_word = determine_overall_signal_word(state.pubchem_data)

    # Section 3: Verified CAS numbers from MASTER_CHEMICAL_DATABASE, PHYSICAL_PROPERTIES, then PubChem
    ingredient_cas_list = []
    for c in state.chemicals:
        name_lower = c.name.lower().strip()
        cas_num = None
        if name_lower in MASTER_CHEMICAL_DATABASE and MASTER_CHEMICAL_DATABASE[name_lower].get("cas_number"):
            cas_num = MASTER_CHEMICAL_DATABASE[name_lower]["cas_number"]
        elif name_lower in PHYSICAL_PROPERTIES:
            cas_num = PHYSICAL_PROPERTIES[name_lower].get("cas")
        else:
            p_data = state.pubchem_data.get(c.name) or {}
            cas_num = p_data.get("cas_number")

        if not cas_num or cas_num == "Data not available":
            for cas_k, name_v in CAS_TO_NAME.items():
                if name_v == name_lower:
                    cas_num = cas_k
                    break

        if not cas_num or cas_num == "Data not available":
            cas_num = "Not Available"

        ingredient_cas_list.append(f"{c.name.title()} (CAS {cas_num}): {c.concentration or 'Not specified'}")

    ingredients_sec3_str = "; ".join(ingredient_cas_list) if ingredient_cas_list else "None specified"

    # Section 7: Dynamically computed storage/handling thermal warnings
    storage_warning_str = _build_thermal_warnings(chem_names, state.hardware)

    # Section 8: Dynamically computed exposure limits for actual chemicals only
    exposure_limits_str = _build_exposure_limits_str(chem_names)

    # Section 9: Dynamically computed physical properties for actual chemicals only
    physical_props_str = _build_physical_props_str(chem_names)

    # Section 14: Transport classification — derived from actual mixture composition
    t_info = get_mixture_un_transport_info(chem_names)
    transport_str = (
        f"UN Number: {t_info['un_number']}, "
        f"Proper Shipping Name: {t_info['shipping_name']}, "
        f"Transport Hazard Class: {t_info['class']}, "
        f"Packing Group: {t_info['packing_group']}, "
        f"Marine Pollutant: {t_info['marine_pollutant']}"
    )

    # Section 11: Carcinogen classification from actual chemicals
    carcinogen_info_list = []
    for c_name in chem_names:
        c_info = get_carcinogen_info(c_name)
        if c_info:
            carcinogen_info_list.append(
                f"{c_name.title()}: IARC {c_info['iarc']}, NTP: {c_info['ntp']}, "
                f"OSHA: {c_info['osha']}, Prop 65: {c_info['prop65']}"
            )

    carcinogen_str = (
        "; ".join(carcinogen_info_list)
        if carcinogen_info_list
        else "No components listed on IARC, NTP, or OSHA carcinogen registries for this formulation."
    )

    lang_names = {
        "en": "English",
        "es": "Spanish (Español)",
        "fr": "French (Français)",
        "de": "German (Deutsch)",
        "ja": "Japanese (日本語)",
    }
    target_lang = lang_names.get(state.language.lower(), "English")

    region_specs = {
        "US": "US OSHA HCS 29 CFR 1910.1200 (2024 Final Rule / GHS Rev 7 alignment)",
        "EU": "EU REACH (EC 1907/2006) & CLP (EC 1272/2008)",
        "JP": "Japan JIS Z 7253:2019 / ISHL",
        "CA": "Canada WHMIS 2015 / HPR",
        "GB": "UK GB-CLP / HSE Regulations",
    }
    target_region_spec = region_specs.get(state.region.upper(), f"GHS Rev.7 ({state.region})")

    # Build a dynamic GHS hazard summary from PubChem data for Section 2
    ghs_hazards_from_pubchem = []
    for p_data in state.pubchem_data.values():
        if isinstance(p_data, dict):
            for stmt in p_data.get("hazard_statements", [])[:5]:
                if stmt and stmt not in ghs_hazards_from_pubchem:
                    ghs_hazards_from_pubchem.append(stmt)

    ghs_hazards_str = "; ".join(ghs_hazards_from_pubchem) if ghs_hazards_from_pubchem else "Refer to individual component SDS"
    pictogram_codes_str = ", ".join(sorted(all_pictograms)) if all_pictograms else "GHS07"

    # Prompt LLM for structured 16 sections — all context is dynamically derived
    prompt = (
        f"Generate an authoritative, {target_region_spec} compliant Safety Data Sheet (SDS) "
        f"for the following chemical formulation.\n"
        f"OUTPUT LANGUAGE: Write ALL section titles and content in {target_lang}.\n\n"
        f"FORMULATION DATA:\n"
        f"  Product: {product_name}\n"
        f"  Ingredients & CAS Numbers (Section 3): {ingredients_sec3_str}\n"
        f"  GHS Signal Word: {signal_word}\n"
        f"  GHS Pictograms: {pictogram_codes_str}\n"
        f"  GHS Hazard Statements (from PubChem): {ghs_hazards_str}\n"
        f"  Physical & Chemical Properties (Section 9): {physical_props_str}\n"
        f"  Exposure Limits (Section 8): {exposure_limits_str}\n"
        f"  Carcinogen Registry Data (Section 11): {carcinogen_str}\n"
        f"  Transport Classification (Section 14): {transport_str}\n"
        f"  Storage & Thermal Hazards (Section 7): {storage_warning_str}\n"
        f"  Operating Hardware & Temperature: {state.hardware}\n"
        f"  PubChem GHS Data: {json.dumps(state.pubchem_data)}\n"
        f"  Compliance Audit Flags: {state.chemical_flags}\n"
        f"  Reflection Feedback (corrections): {state.reflection_notes}\n\n"
        "MANDATORY GHS SDS COMPLIANCE RULES:\n"
        "1. Section 1 MUST begin with: 'DRAFT DOCUMENT — AI-GENERATED FOR REVIEW PURPOSES ONLY. "
        "NOT AN OFFICIAL SDS. Requires review by a qualified Certified Safety Professional (CSP) before operational use. "
        "Emergency Contact: [TO BE VERIFIED AND COMPLETED BY RESPONSIBLE PARTY].'\n"
        "2. Section 2 MUST list ALL applicable GHS hazard pictograms derived from the GHS Pictograms list above, "
        "state the GHS signal word provided, and enumerate all hazard statements from GHS Hazard Statements above.\n"
        "3. Section 3 MUST use ONLY the Ingredients & CAS Numbers provided above. "
        "Do NOT add any other chemicals. Do NOT list exposure limits (PEL, TLV) in Section 3.\n"
        "4. Section 7 MUST include the Storage & Thermal Hazards content provided above verbatim.\n"
        "5. Section 8 MUST list the Exposure Limits provided above for each chemical. "
        "Include specific PPE: chemical-resistant gloves appropriate for each component, splash goggles, "
        "fume hood or respiratory protection if volatile components are present.\n"
        "6. Section 9 MUST list the Physical & Chemical Properties provided above. "
        "Only include data for chemicals in THIS formulation — do not invent properties.\n"
        "7. Section 11 MUST include the Carcinogen Registry Data provided above. "
        "If no carcinogens are listed, state that explicitly.\n"
        "8. Section 14 MUST use the Transport Classification provided above.\n"
        "9. Section 15 MUST cite the applicable regulatory framework for the region and list all relevant statutes "
        "(TSCA, SARA, OSHA, Cal Prop 65 for US; REACH/CLP for EU; WHMIS for CA).\n"
        "10. Section 16 MUST include the revision date, document version, and a disclaimer that this is an AI-draft document.\n\n"
        f"Return ONLY a JSON array of exactly 16 objects, written in {target_lang}.\n"
        "Schema: [{\"section_number\": int (1-16), \"title\": \"string\", \"content\": \"detailed section text\"}]\n"
    )

    try:
        raw_json = await llm_chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are a Certified Safety Professional (CSP) and GHS SDS Author. "
                        f"Write all outputs in {target_lang} for {target_region_spec}. "
                        "Return JSON only. Never invent chemical properties or CAS numbers not provided. "
                        "Only use data from the formulation context provided."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            json_mode=True
        )
        sections_data = json.loads(raw_json)
        sections = []
        for s in sections_data:
            sec_obj = SDSSection.model_validate(s)
            sec_obj.title = _clean_section_title(sec_obj.section_number, sec_obj.title)
            sections.append(sec_obj)
    except Exception as e:
        logger.warning(f"[SDSAuthorAgent] LLM SDS JSON generation failed ({e}). Falling back to structured fallback sections.")
        sections = []
        for num, title in SDS_SECTION_TITLES:
            sections.append(SDSSection(
                section_number=num,
                title=title,
                content=f"Section {num} ({title}): Sourced from OSHA HazCom standards for {product_name}. Expert review required."
            ))

    sds_doc = SDSDocument(
        product_name=product_name,
        revision_date=datetime.date.today().strftime("%B %d, %Y"),
        sections=sections,
        pictogram_codes=list(all_pictograms),
        signal_word=signal_word
    )
    state.sds_document = sds_doc

    # Render Jinja2 HTML
    try:
        with open("templates/sds_template.html", "r", encoding="utf-8") as f:
            template_str = f.read()

        tpl = Template(template_str)
        pic_svgs = []
        for code in sds_doc.pictogram_codes:
            svg_content = load_pictogram_svg(code)
            if svg_content:
                pic_svgs.append(svg_content)

        warning_notes = []
        bw = getattr(state, "boundary_warnings", [])
        if bw:
            warning_notes.extend(bw)
        if state.reflection_notes:
            warning_notes.extend(state.reflection_notes)

        # Deduplicate warnings while preserving order
        seen = set()
        unique_notes = []
        for note in warning_notes:
            if note and note not in seen:
                seen.add(note)
                unique_notes.append(note)

        warning_msg = "\n• ".join(unique_notes) if unique_notes else None
        if warning_msg and not warning_msg.startswith("• "):
            warning_msg = "• " + warning_msg

        state.sds_html = tpl.render(
            sds=sds_doc,
            pictogram_svgs=pic_svgs,
            warning_banner=warning_msg
        )
    except Exception as e:
        logger.error(f"[SDSAuthorAgent] HTML rendering failed: {e}")
        state.sds_html = f"<h3>Error rendering SDS HTML: {e}</h3>"

    duration = int((time.time() - start_time) * 1000)
    state.add_trace(
        agent="SDSAuthoringAgent",
        action="GHS 16-Section Synthesis & HTML Render",
        observation=f"Generated SDS Document with {len(sds_doc.sections)} sections. Signal Word: {signal_word}",
        duration_ms=duration,
        status="success"
    )
    return state
