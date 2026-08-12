# ChemShield AI — Product Overview

## The Problem We Solve

Every organization that formulates, handles, or ships chemical products is legally required to:

1. **Comply with OSHA HazCom 2012** — Evaluate every ingredient against permissible exposure limits (PELs), provide worker training, and maintain compliant Safety Data Sheets (SDS).
2. **Author GHS-compliant SDS documents** — A 16-section document mandated by the UN Globally Harmonized System of Classification and Labelling of Chemicals (GHS), containing hazard classifications, first-aid measures, firefighting information, exposure controls, transport data, and regulatory status.
3. **Evaluate equipment compatibility** — Confirm that containers and laboratory equipment can safely handle the formulation at its operating temperature.

**Today, this process is:**
- Slow — a trained chemical safety professional (CSP) spends 2–4 hours per formulation
- Error-prone — manual lookups from OSHA tables, NIST databases, and IARC registries
- Expensive — certified CSP labor costs $80–$150/hour
- Inconsistent — different reviewers apply different standards

**ChemShield AI automates this entire workflow in under 30 seconds.**

---

## Who Is This For?

| User Type | How They Use ChemShield |
|-----------|------------------------|
| **Chemical formulators** (small labs, R&D) | Quickly check if a new formulation is OSHA-compliant before scaling up |
| **Manufacturing QA/safety teams** | Batch-audit all formulations in an existing product portfolio |
| **Regulatory affairs professionals** | Draft and export GHS SDS documents for supplier submission |
| **Lab safety officers** | Verify that heating protocols and container choices are thermally safe |
| **Supply chain auditors** | Verify UN transport classifications for dangerous goods shipping |

---

## What ChemShield AI Does

### Step 1: Natural Language Input
The user enters a formulation description in plain language — no special format required:
> *"94% Water, 6% Benzene. Heated to 120°C in a soda-lime glass beaker."*

Or a CAS number:
> *"CAS 71-43-2 at 0.5 ppm in water, stored at 25°C in a polypropylene container."*

### Step 2: Multi-Agent OSHA Compliance Audit
A specialized AI agent pipeline runs in parallel:
- **Chemical Compliance**: Looks up OSHA PEL, STEL, and ceiling limits for each chemical using a 5-tier data retrieval strategy
- **Hardware Compatibility**: Checks equipment thermal safety limits via the FastMCP hardware tool
- **PubChem Intelligence**: Fetches GHS hazard classifications, pictograms, and CAS numbers from the PubChem database

### Step 3: Safety Verdict & Executive Summary
The Supervisor produces:
- A binary safety verdict: **COMPLIANT** or **NON_COMPLIANT**
- A plain-language executive summary explaining the findings
- A flag-by-flag breakdown with regulatory limits, detected values, and sources

### Step 4: GHS SDS Generation
If the user requests an SDS, the system generates all 16 mandatory GHS sections including:
- Signal word (DANGER or WARNING, computed from GHS H-codes)
- All applicable GHS pictograms
- Exposure controls and PPE requirements
- UN transport classification
- IARC/NTP carcinogen disclosures
- Emergency contact and responsible party information

### Step 5: 9-Point Reflection Audit
A Reflection Agent automatically audits the generated SDS against 9 quality criteria. If any check fails, the SDS is re-authored with correction notes until it passes or the retry limit is reached.

---

## How We Are Different

| Feature | ChemShield AI | Traditional CSP | Generic LLM (ChatGPT) |
|---------|--------------|-----------------|----------------------|
| OSHA regulatory data source | Hardcoded + OSHA RAG + PubChem | Manual lookup | No authoritative source |
| SDS generation | 16 sections, GHS Rev.9, verified | 2–4 hours per SDS | Unverified, no citations |
| GHS pictograms | Accurate H-code → pictogram mapping | Manual selection | Often incorrect |
| Hardware safety check | FastMCP thermal limit tool | Manual ASTM reference | No capability |
| CAS number support | Yes — auto-resolved to name | Yes | Inconsistent |
| Fail-closed behavior | Yes — unknown = REVIEW_REQUIRED | Yes (manual review) | No — defaults to "safe" |
| Audit trail | Full agent execution trace | Paper trail | No trace |
| Response time | < 30 seconds | 2–4 hours | Fast but unreliable |
| Cost per formulation | ~$0.05 API cost | $200–$400 CSP time | No guarantee of correctness |

---

## System Capabilities

### Supported Chemicals
Over **22 OSHA-regulated chemicals** in the hardcoded master database, plus unlimited coverage through PubChem API and web search for exotic compounds.

### Supported Regulatory Frameworks
- **US**: OSHA HazCom 2012 (29 CFR 1910.1200), PELs from Table Z-1/Z-2 and chemical-specific standards
- **EU**: ECHA REACH / CLP Regulation (via Gemini knowledge + Tavily search)
- **CA**: WHMIS 2015 (via Gemini knowledge + Tavily search)
- **GB**: HSE COSHH / UK CLP (via Gemini knowledge + Tavily search)
- **JP**: JIS Z 7253 (via Gemini knowledge + Tavily search)

### Supported Hardware Types
12 lab equipment types with authoritative thermal limits:
- Soda-lime glass (100°C), Borosilicate glass (500°C)
- Polypropylene (80°C), PTFE/Teflon (260°C)
- Stainless steel (600°C)
- Plus unlimited coverage via web search fallback

### SDS Output
- 16 mandatory GHS sections
- HTML preview + PDF download
- Available in English, Spanish, French, German, Japanese
- DRAFT watermark (production use requires CSP review)

---

## System Limitations

> **Important**: ChemShield AI is a decision-support tool, not a replacement for a licensed chemical safety professional (CSP).

1. **Not a substitute for CSP review**: The generated SDS is clearly marked "DRAFT — AI-GENERATED FOR REVIEW PURPOSES ONLY." Before any SDS is used for regulatory submission or worker training, it must be reviewed by a qualified safety professional.

2. **Regulatory coverage**: The hardcoded master database covers 22 chemicals. For exotic or novel compounds, the system relies on Gemini AI knowledge and web search, which carry higher uncertainty.

3. **Concentration unit ambiguity**: When a user provides a liquid formulation percentage (e.g., 6%) but OSHA only has an airborne ppm limit, the system returns `REVIEW_REQUIRED` because the comparison is scientifically undefined. A CSP must determine the actual airborne exposure level at the use conditions.

4. **Regulatory jurisdiction limits**: EU, CA, and GB regulatory lookups use Gemini AI knowledge and web search rather than hardcoded values. These should be verified against the official ECHA, Health Canada, and HSE databases.

5. **PubChem availability**: PubChem is a free public API with rate limits. High-traffic usage may encounter rate limiting for large formulations.

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend API | FastAPI (Python) |
| Multi-agent orchestration | Custom ReAct supervisor loop |
| LLM provider | Google Gemini (configurable via OpenRouter) |
| Chemical data | PubChem API, OSHA RAG (ChromaDB), NIST |
| Hardware safety tool | FastMCP stdio transport |
| Vector database | ChromaDB (local persistence) |
| Semantic cache | SQLite |
| Web search fallback | Tavily API |
| Frontend | HTML5, Vanilla CSS, JavaScript |
| Font | Space Grotesk + Inter (Google Fonts) |

---

## Roadmap

Near-term improvements planned:

1. **Mixture exposure limit calculator**: Given individual component PELs, compute the combined OSHA mixture exposure limit using the additive formula (OSHA 29 CFR 1910.1000(d)(2)(i)).
2. **SDS revision tracking**: Version-controlled SDS documents with diff view between revisions.
3. **Batch formulation audit**: Upload a CSV or spreadsheet of multiple formulations for bulk OSHA audit.
4. **REACH SVHC lookup**: Automatically check if any ingredient appears on the EU REACH Substances of Very High Concern (SVHC) candidate list.
5. **GHS label generator**: Generate the physical GHS label (with pictograms, signal word, hazard statements) for direct printing.
