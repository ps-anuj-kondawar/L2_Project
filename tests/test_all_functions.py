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


if __name__ == "__main__":
    unittest.main()

