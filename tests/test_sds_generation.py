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
        sections = [{"section_number": i, "title": f"Section {i}", "content": f"Detailed content for section {i}"} for i in range(1, 17)]
        return json.dumps(sections)

    return "Safety summary finding."


class TestSDSGeneration(unittest.IsolatedAsyncioTestCase):

    async def test_pubchem_client_benzene(self):
        data = await get_pubchem_data("benzene")
        self.assertIsNotNone(data.cid)
        self.assertEqual(data.cas_number, "71-43-2")
        self.assertIn("GHS02", data.ghs_pictogram_codes)
        self.assertEqual(data.signal_word, "DANGER")

    @patch("src.agents.hardware_agent._mcp_check")
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
        self.assertGreater(len(result.trace), 0)


if __name__ == "__main__":
    unittest.main()
