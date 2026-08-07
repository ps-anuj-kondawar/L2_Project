import unittest
import json
from unittest.mock import patch, AsyncMock
from src.agents.supervisor import run_supervisor
from src.infrastructure.pubchem_client import get_pubchem_data

async def mock_sds_llm_chat(messages, json_mode=False):
    sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")

    if "chemical entity extractor" in sys_msg or "Extract all chemicals" in user_msg:
        return '{"chemicals": [{"name": "Benzene", "concentration": "6%"}, {"name": "Water", "concentration": "94%"}], "hardware": [{"name": "borosilicate glass beaker", "target_temperature_celsius": 50.0}]}'

    if "multi-agent policy router" in sys_msg or "Supervisor AI Policy" in user_msg:
        return '{"action": "finish_audit", "reasoning": "Finished audit"}'

    if "SDS Author" in sys_msg or "Generate an authoritative" in user_msg:
        sections = []
        for i in range(1, 17):
            content = f"Detailed content for section {i}."
            if i == 1:
                content = "DRAFT DOCUMENT — AI-GENERATED FOR REVIEW PURPOSES ONLY. Emergency Phone: CHEMTREC 1-800-424-9300 or [TO BE COMPLETED BY RESPONSIBLE PARTY]."
            elif i == 3:
                content = "Composition: Benzene (CAS 71-43-2), Water."
            elif i == 8:
                content = "Exposure limits: OSHA PEL 1 ppm TWA. Wear chemical splash goggles, Viton gloves, and use fume hood PPE."
            elif i == 14:
                content = "Transport Classification: UN1114 BENZENE SOLUTION Class 3 Packing Group II."
            elif i == 15:
                content = "Regulatory Information: Regulated under TSCA, SARA Title III, OSHA, and Cal Prop 65."
            sections.append({"section_number": i, "title": f"Section {i}", "content": content})
        return json.dumps(sections)

    return "Safety summary finding."


class TestSDSGeneration(unittest.IsolatedAsyncioTestCase):

    @patch("src.infrastructure.pubchem_client._fetch_json", new_callable=AsyncMock)
    async def test_pubchem_client_benzene(self, mock_fetch):
        mock_fetch.side_effect = [
            {"IdentifierList": {"CID": [241]}},
            {"InformationList": {"Information": [{"RegistryID": ["71-43-2"]}]}},
            {"PropertyTable": {"Properties": [{"MolecularWeight": 78.11, "BoilingPoint": 80.1}]}},
            {"Record": {"Section": [{"TOCHeading": "GHS Classification", "Section": [{"TOCHeading": "Signal", "Information": [{"Value": {"StringWithMarkup": [{"String": "DANGER"}]}}]}, {"TOCHeading": "Pictogram", "Information": [{"Value": {"StringWithMarkup": [{"String": "GHS02"}]}}]}]}]}}
        ]
        data = await get_pubchem_data("benzene_test_offline")
        self.assertIsNotNone(data.cid)
        self.assertEqual(data.cas_number, "71-43-2")
        self.assertIn("GHS02", data.ghs_pictogram_codes)
        self.assertEqual(data.signal_word, "DANGER")

    @patch("src.agents.hardware_agent._mcp_check", new_callable=AsyncMock)
    @patch("src.agents.supervisor.get_semantic_cache", return_value=None)
    @patch("src.agents.supervisor.llm_chat", new=AsyncMock(side_effect=mock_sds_llm_chat))
    @patch("src.agents.sds_author_agent.llm_chat", new=AsyncMock(side_effect=mock_sds_llm_chat))
    async def test_sds_generation_full_pipeline(self, mock_cache, mock_mcp):
        mock_mcp.return_value = ({"equipment_name": "borosilicate glass beaker", "target_temperature_celsius": 50.0, "max_safe_temperature_celsius": 500.0, "is_safe": True, "status": "SAFE"}, True, True)
        input_text = "Formula A-1: 94% Water, 6% Benzene. Heated to 50C in a borosilicate glass beaker."
        result = await run_supervisor(input_text, intent="full")
        self.assertIsNotNone(result.sds_document)
        self.assertEqual(len(result.sds_document.sections), 16)
        self.assertIsNotNone(result.sds_html)
        self.assertIn("Safety Data Sheet", result.sds_html)
        self.assertTrue(result.reflection_passed)
        self.assertGreater(len(result.trace), 0)


if __name__ == "__main__":
    unittest.main()
