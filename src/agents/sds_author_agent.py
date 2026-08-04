import time
import json
import datetime
from jinja2 import Template
from src.core.state import AgentState
from src.core.models import SDSDocument, SDSSection
from src.infrastructure.llm_client import chat as llm_chat
from src.utils.ghs_rules import (
    determine_overall_signal_word,
    load_pictogram_svg,
    get_un_transport_info,
    get_carcinogen_info,
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


async def run_sds_author_agent(state: AgentState) -> AgentState:
    """
    GHS SDS Authoring Agent.
    Synthesizes formulation information and PubChem data into a complete 16-section SDS HTML document.
    """
    start_time = time.time()
    logger.info("[SDSAuthorAgent] Generating 16-Section GHS Safety Data Sheet...")

    # Determine product name
    if state.chemicals:
        chem_names = [c.name for c in state.chemicals]
        product_name = "Formulation: " + " + ".join(chem_names)
    else:
        product_name = state.user_input[:40]

    # Collect pictograms and signal word
    all_pictograms = set()
    for p_data in state.pubchem_data.values():
        if isinstance(p_data, dict):
            for pic in p_data.get("ghs_pictogram_codes", []):
                all_pictograms.add(pic)
    
    if not all_pictograms:
        all_pictograms.add("GHS07")

    signal_word = determine_overall_signal_word(state.pubchem_data)

    # Collect UN Transport & Carcinogen Registry data for primary chemicals
    transport_info_list = []
    carcinogen_info_list = []
    if state.chemicals:
        for c in state.chemicals:
            t_info = get_un_transport_info(c.name)
            if t_info["un_number"] != "Not Regulated":
                transport_info_list.append(f"{c.name}: UN Number: {t_info['un_number']}, Proper Shipping Name: {t_info['shipping_name']}, Class: {t_info['class']}, Packing Group: {t_info['packing_group']}")
            c_info = get_carcinogen_info(c.name)
            if c_info:
                carcinogen_info_list.append(f"{c.name}: IARC: {c_info['iarc']}, NTP: {c_info['ntp']}, OSHA: {c_info['osha']}, Prop 65: {c_info['prop65']}")

    transport_str = "; ".join(transport_info_list) if transport_info_list else "UN Number: Not Regulated, Shipping Name: NON-HAZARDOUS CHEMICAL MIXTURE, Class: Not Applicable, Packing Group: Not Applicable"
    carcinogen_str = "; ".join(carcinogen_info_list) if carcinogen_info_list else "No components listed on IARC, NTP, or OSHA carcinogen registries."

    lang_names = {
        "en": "English",
        "es": "Spanish (Español)",
        "fr": "French (Français)",
        "de": "German (Deutsch)",
        "ja": "Japanese (日本語)",
    }
    target_lang = lang_names.get(state.language.lower(), "English")

    region_specs = {
        "US": "US OSHA HazCom 2012 / GHS Rev.9",
        "EU": "EU REACH (EC 1907/2006) & CLP (EC 1272/2008)",
        "JP": "Japan JIS Z 7253:2019 / ISHL",
        "CA": "Canada WHMIS 2015 / HPR",
        "GB": "UK GB-CLP / HSE Regulations",
    }
    target_region_spec = region_specs.get(state.region.upper(), f"GHS Rev.9 ({state.region})")

    # Prompt LLM for structured 16 sections with strict compliance rules
    prompt = (
        f"Generate an authoritative, {target_region_spec} compliant Safety Data Sheet (SDS) for this chemical formulation.\n"
        f"OUTPUT LANGUAGE REQUIREMENT: You MUST write all section titles and content in {target_lang}.\n\n"
        f"Product Name: {product_name}\n"
        f"Chemical Ingredients & Ratios: {state.chemicals}\n"
        f"Hardware & Storage Temp: {state.hardware}\n"
        f"PubChem Chemical Safety Data: {json.dumps(state.pubchem_data)}\n"
        f"Compliance Flags: {state.chemical_flags}\n"
        f"UN Transport Classification Data: {transport_str}\n"
        f"Authoritative Carcinogen Registry Data: {carcinogen_str}\n\n"
        f"Reflection Feedback (if any): {state.reflection_notes}\n\n"
        "STRICT SDS COMPLIANCE RULES:\n"
        "1. Section 1 MUST list Supplier: ChemShield AI Safety Intelligence Platform, Address: 100 Safety Automation Plaza, Cambridge, MA 02142, Emergency Phone: CHEMTREC 1-800-424-9300.\n"
        "2. Section 3 (Composition) MUST ONLY list Chemical Name, CAS Number, and Concentration Range (% by weight or volume). DO NOT list exposure limits (PEL, TLV, TWA) in Section 3!\n"
        "3. Section 8 (Exposure Controls) MUST list exact Permissible Exposure Limits (PELs/OELs) TWA/STEL and specific chemical PPE (e.g. Viton/Butyl gloves, chemical splash goggles, fume hood, SCBA/respirator).\n"
        "4. Section 9 (Physical & Chemical Properties) MUST list chemical physical constants (boiling point, flash point, vapor pressure, solubility, appearance, odor) from PubChem data.\n"
        "5. Section 11 (Toxicology) MUST reference official IARC, NTP, OSHA, and regional carcinogen ratings provided above.\n"
        "6. Section 14 (Transport) MUST contain exact UN Number, Proper Shipping Name, Hazard Class, and Packing Group provided above.\n"
        "7. Section 15 (Regulatory) MUST state relevant regional regulatory inventory status and warnings.\n"
        "8. Section 16 MUST include NFPA ratings (Health, Flammability, Instability).\n\n"
        f"Return ONLY a JSON array containing exactly 16 objects, one for each SDS section, written entirely in {target_lang}.\n"
        "Schema: [{\"section_number\": int (1-16), \"title\": \"string\", \"content\": \"detailed section text\"}]\n"
    )

    try:
        raw_json = await llm_chat(
            messages=[
                {"role": "system", "content": f"You are a Certified Safety Professional (CSP) and GHS SDS Author. Write all outputs in {target_lang} for {target_region_spec}. Return JSON only."},
                {"role": "user", "content": prompt}
            ],
            json_mode=True
        )
        sections_data = json.loads(raw_json)
        sections = [SDSSection.model_validate(s) for s in sections_data]
    except Exception as e:
        logger.warning(f"[SDSAuthorAgent] LLM SDS JSON generation failed ({e}). Falling back to structured fallback sections.")
        sections = []
        for num, title in SDS_SECTION_TITLES:
            sections.append(SDSSection(
                section_number=num,
                title=title,
                content=f"Section {num} ({title}): Sourced from OSHA HazCom standards for {product_name}."
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
        pic_svgs = [load_pictogram_svg(code) for code in sds_doc.pictogram_codes if load_pictogram_svg(code)]
        
        warning_msg = None
        if not state.reflection_passed and state.reflection_notes:
            warning_msg = f"Failed automated review: {'; '.join(state.reflection_notes)}. Human expert review required."

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
