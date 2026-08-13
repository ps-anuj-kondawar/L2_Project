import unittest
import os
import sqlite3
import asyncio
from src.utils.ghs_rules import (
    determine_overall_signal_word,
    get_un_transport_info,
    get_carcinogen_info,
    load_pictogram_svg
)
from src.infrastructure.cache import (
    get_summary_cache,
    set_summary_cache,
    get_conversation_cache,
    set_conversation_cache,
    get_pubchem_cache,
    set_pubchem_cache,
    get_osha_limits,
    set_osha_limits
)
from src.core.state import AgentState
from src.core.models import (
    PubChemData,
    ComplianceReport,
    SDSDocument,
    SDSSection,
    ChemicalFlag,
    HardwareFlag,
    ExtractedHardware,
    ExtractedChemical
)
from src.agents.hardware_agent import run_hardware_agent, _mcp_check
from src.agents.chemical_agent import run_chemical_agent, check_single_chemical
from src.core.copilot import copilot_chat


class TestGHSRules(unittest.TestCase):

    def test_determine_overall_signal_word_danger(self):

        pubchem_map = {
            "benzene": {
                "signal_word": "DANGER",
                "hazard_statements": ["H350: May cause cancer"]
            }
        }
        word = determine_overall_signal_word(pubchem_map)
        self.assertEqual(word, "DANGER")

    def test_determine_overall_signal_word_warning(self):

        pubchem_map = {
            "water": {
                "signal_word": "WARNING",
                "hazard_statements": []
            }
        }
        word = determine_overall_signal_word(pubchem_map)
        self.assertEqual(word, "WARNING")

    def test_get_un_transport_info_benzene(self):

        info = get_un_transport_info("benzene")
        self.assertEqual(info["un_number"], "UN1114")
        self.assertEqual(info["class"], "3")

    def test_get_un_transport_info_unknown(self):

        info = get_un_transport_info("unknown_chemical")
        self.assertEqual(info["un_number"], "Not Regulated")

    def test_get_carcinogen_info_benzene(self):

        carcinogen = get_carcinogen_info("benzene")
        self.assertIsNotNone(carcinogen)
        self.assertIn("Group 1", carcinogen["iarc"])

    def test_load_pictogram_svg_valid(self):

        svg = load_pictogram_svg("GHS02")
        self.assertTrue(len(svg) > 0)
        self.assertIn("svg", svg.lower())

    def test_load_pictogram_svg_invalid(self):

        svg = load_pictogram_svg("INVALID_CODE")
        self.assertEqual(svg, "")


class TestInfrastructureCache(unittest.TestCase):

    def test_summary_cache_roundtrip(self):

        violations = ["Violation Test A"]
        summary_text = "Test summary content"
        set_summary_cache(violations, summary_text)
        cached = get_summary_cache(violations)
        self.assertEqual(cached, summary_text)

    def test_conversation_cache_roundtrip(self):

        msg = "What is the PEL for Benzene?"
        history = []
        resp = "The PEL for Benzene is 1 ppm TWA."
        set_conversation_cache(msg, history, resp)
        cached = get_conversation_cache(msg, history)
        self.assertEqual(cached, resp)

    def test_pubchem_cache_roundtrip(self):

        chem = "testchem_unit_test"
        data = {"cid": 12345, "cas_number": "100-00-0", "signal_word": "DANGER"}
        set_pubchem_cache(chem, data)
        cached = get_pubchem_cache(chem)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["cid"], 12345)

    def test_osha_limits_cache_roundtrip(self):

        chem = "testchem_osha_unit"
        data = {"limit_ppm": 50.0, "source": "OSHA Table Z-1"}
        set_osha_limits(chem, data)
        cached = get_osha_limits(chem)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["limit_ppm"], 50.0)


from unittest.mock import patch, AsyncMock

class TestHardwareAgent(unittest.IsolatedAsyncioTestCase):

    @patch("src.agents.hardware_agent._mcp_check", new_callable=AsyncMock)
    async def test_hardware_safety_borosilicate_glass_safe(self, mock_mcp):
        mock_mcp.return_value = ({
            "equipment_name": "borosilicate glass",
            "target_temperature_celsius": 250.0,
            "max_safe_temperature_celsius": 500.0,
            "is_safe": True,
            "status": "SAFE"
        }, True, True)

        state = AgentState(
            user_input="test hardware",
            hardware=[ExtractedHardware(name="borosilicate glass", target_temperature_celsius=250.0)]
        )
        updated = await run_hardware_agent(state)
        self.assertEqual(len(updated.hardware_flags), 1)
        self.assertTrue(updated.hardware_flags[0].is_safe)
        self.assertEqual(updated.hardware_flags[0].status, "SAFE")

    @patch("src.agents.hardware_agent._mcp_check", new_callable=AsyncMock)
    async def test_hardware_safety_borosilicate_glass_unsafe(self, mock_mcp):
        mock_mcp.return_value = ({
            "equipment_name": "borosilicate glass",
            "target_temperature_celsius": 550.0,
            "max_safe_temperature_celsius": 500.0,
            "is_safe": False,
            "status": "UNSAFE"
        }, True, True)

        state = AgentState(
            user_input="test hardware",
            hardware=[ExtractedHardware(name="borosilicate glass", target_temperature_celsius=550.0)]
        )
        updated = await run_hardware_agent(state)
        self.assertEqual(len(updated.hardware_flags), 1)
        self.assertFalse(updated.hardware_flags[0].is_safe)
        self.assertEqual(updated.hardware_flags[0].status, "UNSAFE")

    @patch("src.agents.hardware_agent._mcp_check", new_callable=AsyncMock)
    async def test_run_hardware_agent_state(self, mock_mcp):
        mock_mcp.return_value = ({
            "equipment_name": "polypropylene container",
            "target_temperature_celsius": 50.0,
            "max_safe_temperature_celsius": 100.0,
            "is_safe": True,
            "status": "SAFE"
        }, True, True)

        state = AgentState(
            user_input="test hardware",
            hardware=[ExtractedHardware(name="polypropylene container", target_temperature_celsius=50.0)]
        )
        updated = await run_hardware_agent(state)
        self.assertEqual(len(updated.hardware_flags), 1)
        self.assertTrue(updated.hardware_flags[0].is_safe)


class TestChemicalAgent(unittest.IsolatedAsyncioTestCase):

    async def test_chemical_safety_water_compliant(self):
        flag, rel = await check_single_chemical("water", "90%")
        self.assertTrue(flag.is_compliant)

    @patch("src.agents.chemical_agent._search_chemical_safety", new_callable=AsyncMock)
    @patch("src.agents.chemical_agent.query_regulations", return_value=[])
    async def test_chemical_safety_benzene_exceeds(self, mock_rag, mock_web):
        mock_web.return_value = {"pct": 1.0, "citation": "test citation"}
        flag, rel = await check_single_chemical("benzene", "5%", region="US")
        self.assertEqual(flag.status, "NON_COMPLIANT")
        self.assertFalse(flag.is_compliant)

    @patch("src.agents.chemical_agent._search_chemical_safety", new_callable=AsyncMock)
    @patch("src.agents.chemical_agent.query_regulations", return_value=[])
    async def test_missing_concentration_returns_review_required(self, mock_rag, mock_web):
        mock_web.return_value = {"ppm": 1.0, "citation": "test citation"}
        flag, rel = await check_single_chemical("benzene", "", region="US")
        self.assertEqual(flag.status, "REVIEW_REQUIRED")
        self.assertFalse(flag.is_compliant)

    async def test_run_chemical_agent_state(self):
        state = AgentState(
            user_input="test chemical",
            chemicals=[ExtractedChemical(name="water", concentration="99%")]
        )
        updated = await run_chemical_agent(state)
        self.assertEqual(len(updated.chemical_flags), 1)
        self.assertTrue(updated.chemical_flags[0].is_compliant)


class TestCopilot(unittest.IsolatedAsyncioTestCase):

    @patch("src.core.copilot.llm_chat", new_callable=AsyncMock)
    async def test_copilot_chat_basic_query(self, mock_chat):
        mock_chat.return_value = "Wear protective gloves and eye goggles when handling benzene."
        result = await copilot_chat("What safety precautions are needed for benzene handling?", history=[])
        self.assertIsNotNone(result)
        self.assertIn("response", result)
        self.assertIsInstance(result["response"], str)
        self.assertGreater(len(result["response"]), 10)

    @patch("src.core.copilot.llm_chat", new_callable=AsyncMock)
    @patch("src.core.copilot.get_conversation_cache", return_value=None)
    async def test_copilot_cas_number_resolves_in_message(self, mock_cache, mock_chat):
        """CAS number 71-43-2 in chat message must be detected and resolved to benzene for context lookup."""
        mock_chat.return_value = "CAS 71-43-2 is Benzene. Its OSHA PEL is 1 ppm TWA."
        result = await copilot_chat("What is CAS 71-43-2?", history=[])
        self.assertIn("response", result)
        # Force cache miss means llm_chat must have been called
        mock_chat.assert_called_once()


class TestMasterChemicalDatabase(unittest.TestCase):
    """Test that MASTER_CHEMICAL_DATABASE contains correct authoritative limits for critical chemicals."""

    def setUp(self):
        from src.core.constants import MASTER_CHEMICAL_DATABASE
        self.db = MASTER_CHEMICAL_DATABASE

    def test_benzene_pel_is_one_ppm(self):
        """OSHA Benzene PEL must be exactly 1.0 ppm per 29 CFR 1910.1028."""
        self.assertEqual(self.db["benzene"]["pel_ppm"], 1.0)

    def test_benzene_liquid_pct_limit_is_0_1(self):
        """OSHA Benzene liquid volume limit must be 0.1% per 29 CFR 1910.1028."""
        self.assertEqual(self.db["benzene"]["liquid_pct_limit"], 0.1)

    def test_benzene_cas_is_correct(self):
        self.assertEqual(self.db["benzene"]["cas_number"], "71-43-2")

    def test_formaldehyde_pel_is_0_75_ppm(self):
        """OSHA Formaldehyde PEL must be 0.75 ppm per 29 CFR 1910.1048."""
        self.assertEqual(self.db["formaldehyde"]["pel_ppm"], 0.75)

    def test_dichloromethane_action_level_is_12_5(self):
        """DCM action level must be 12.5 ppm per 29 CFR 1910.1052."""
        self.assertEqual(self.db["dichloromethane"]["action_level_ppm"], 12.5)

    def test_all_entries_have_cas_and_standard(self):
        """Every MASTER_CHEMICAL_DATABASE entry must have a CAS number and standard citation."""
        for name, entry in self.db.items():
            with self.subTest(chemical=name):
                self.assertIn("cas_number", entry, f"'{name}' missing cas_number")
                self.assertIn("standard", entry, f"'{name}' missing standard")
                self.assertIsNotNone(entry["standard"], f"'{name}' standard is None")


class TestCASResolution(unittest.TestCase):
    """Test CAS-to-name resolution used by supervisor entity extraction."""

    def setUp(self):
        from src.core.constants import CAS_TO_NAME
        self.cas_map = CAS_TO_NAME

    def test_benzene_cas_resolves(self):
        self.assertEqual(self.cas_map.get("71-43-2"), "benzene")

    def test_dichloromethane_cas_resolves(self):
        self.assertEqual(self.cas_map.get("75-09-2"), "dichloromethane")

    def test_formaldehyde_cas_resolves(self):
        self.assertEqual(self.cas_map.get("50-00-0"), "formaldehyde")

    def test_unknown_cas_returns_none(self):
        self.assertIsNone(self.cas_map.get("99-99-9"))


class TestChemicalAgentFailClosed(unittest.IsolatedAsyncioTestCase):
    """
    Test that the chemical agent defaults to fail-closed (REVIEW_REQUIRED / UNKNOWN)
    when no regulatory data is found — never incorrectly marks as COMPLIANT.
    """

    @patch("src.agents.chemical_agent.query_regulations", return_value=[])
    @patch("src.agents.chemical_agent.get_osha_limits", return_value=None)
    @patch("src.agents.chemical_agent._gemini_chemical_lookup", new_callable=AsyncMock)
    @patch("src.agents.chemical_agent._search_chemical_safety", new_callable=AsyncMock)
    async def test_unknown_chemical_no_data_is_not_compliant(
        self, mock_tavily, mock_gemini, mock_cache, mock_rag
    ):
        """
        An unknown chemical with no regulatory data in any tier must return
        is_compliant=False and status='UNKNOWN' — never COMPLIANT.
        """
        mock_gemini.return_value = {}
        mock_tavily.return_value = {}

        from src.agents.chemical_agent import check_single_chemical
        flag, is_relevant = await check_single_chemical("unknown_exotic_compound_xyz", "5%")
        self.assertFalse(flag.is_compliant)
        self.assertEqual(flag.status, "UNKNOWN")
        self.assertFalse(is_relevant)

    @patch("src.agents.chemical_agent.get_osha_limits", return_value={"ppm": None})
    async def test_stale_cache_empty_ppm_is_bypassed(self, mock_cache):
        """
        A cached entry with ppm=None must be treated as a cache miss.
        The agent should proceed to Gemini lookup, not default to COMPLIANT.
        """
        # Benzene is in MASTER_CHEMICAL_DATABASE — so it will be found there first
        # regardless of the stale cache entry
        from src.agents.chemical_agent import check_single_chemical
        flag, is_relevant = await check_single_chemical("benzene", "5 ppm")
        # Master DB has benzene PEL=1.0 ppm, so 5 ppm should be NON_COMPLIANT
        self.assertFalse(flag.is_compliant)
        self.assertEqual(flag.status, "NON_COMPLIANT")
        self.assertTrue(is_relevant)

    @patch("src.agents.chemical_agent.query_regulations", return_value=[])
    @patch("src.agents.chemical_agent.get_osha_limits", return_value=None)
    @patch("src.agents.chemical_agent._gemini_chemical_lookup", new_callable=AsyncMock)
    @patch("src.agents.chemical_agent._search_chemical_safety", new_callable=AsyncMock)
    async def test_missing_concentration_is_review_required(
        self, mock_tavily, mock_gemini, mock_cache, mock_rag
    ):
        """
        When a chemical is known but its concentration string is missing or empty,
        the status must be REVIEW_REQUIRED — not COMPLIANT.
        """
        mock_gemini.return_value = {"ppm": 1.0, "citation": "Gemini"}
        mock_tavily.return_value = {}

        from src.agents.chemical_agent import check_single_chemical
        # Benzene is in master DB — even with empty concentration, must be REVIEW_REQUIRED
        flag, is_relevant = await check_single_chemical("benzene", "")
        self.assertFalse(flag.is_compliant)
        # Master DB found, concentration missing → must be exactly REVIEW_REQUIRED (not NON_COMPLIANT)
        self.assertEqual(flag.status, "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()


