import unittest
import asyncio
import json
from src.agents.supervisor import run_supervisor

from unittest.mock import patch, AsyncMock

async def mock_llm_chat(messages, json_mode=False):
    sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")

    if "chemical entity extractor" in sys_msg or "Extract all chemicals" in user_msg:
        form_text = user_msg.split("Text:\n")[-1] if "Text:\n" in user_msg else user_msg
        chems = []
        if "Benzene" in form_text or "benzene" in form_text:
            if "0.05%" in form_text:
                conc = "0.05%"
            elif "0.5 ppm" in form_text:
                conc = "0.5 ppm"
            elif "5 ppm" in form_text:
                conc = "5 ppm"
            elif "6%" in form_text:
                conc = "6%"
            else:
                conc = "1%"
            chems.append({"name": "Benzene", "concentration": conc})
        if "Water" in form_text or "water" in form_text:
            chems.append({"name": "Water", "concentration": "90%"})
        if "Acetone" in form_text or "acetone" in form_text:
            conc = "1500 ppm" if "1500" in form_text else "500 ppm"
            chems.append({"name": "Acetone", "concentration": conc})

        hws = []
        if "borosilicate" in form_text:
            hws.append({"name": "borosilicate glass beaker", "target_temperature_celsius": 50.0})
        elif "polypropylene" in form_text:
            temp = 60.0 if "60C" in form_text else 25.0
            hws.append({"name": "polypropylene container", "target_temperature_celsius": temp})
        elif "soda-lime" in form_text:
            temp = 120.0 if "120C" in form_text else 80.0
            hws.append({"name": "soda-lime glass beaker", "target_temperature_celsius": temp})

        return f'{{"chemicals": {json.dumps(chems)}, "hardware": {json.dumps(hws)}}}'

    if "multi-agent policy router" in sys_msg or "Supervisor AI Policy" in user_msg:
        if "check_chemical_compliance" in user_msg and "chemical" not in user_msg.split("Completed Actions: ")[1].split(".")[0]:
            return '{"action": "check_chemical_compliance", "reasoning": "Audit chemical compliance"}'
        if "check_hardware_compatibility" in user_msg and "hardware" not in user_msg.split("Completed Actions: ")[1].split(".")[0]:
            return '{"action": "check_hardware_compatibility", "reasoning": "Audit hardware thermal safety"}'
        return '{"action": "finish_audit", "reasoning": "All checks completed"}'

    return "Automated test safety findings summary."


@patch("src.agents.supervisor.get_semantic_cache", return_value=None)
@patch("src.agents.supervisor.llm_chat", new=AsyncMock(side_effect=mock_llm_chat))
class TestFormulationCompliance(unittest.IsolatedAsyncioTestCase):

    @patch("src.agents.hardware_agent._mcp_check")
    async def test_benzene_volume_exceeds_limit(self, mock_mcp, mock_cache):
        mock_mcp.return_value = ({"equipment_name": "borosilicate glass beaker", "target_temperature_celsius": 50.0, "max_safe_temperature_celsius": 500.0, "is_safe": True, "status": "SAFE"}, True, True)
        input_text = "Formula A-1: 94% Water, 6% Benzene. Heated to 50C in a borosilicate glass beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    @patch("src.agents.hardware_agent._mcp_check")
    async def test_benzene_volume_compliant(self, mock_mcp, mock_cache):
        mock_mcp.return_value = ({"equipment_name": "borosilicate glass beaker", "target_temperature_celsius": 50.0, "max_safe_temperature_celsius": 500.0, "is_safe": True, "status": "SAFE"}, True, True)
        input_text = "Formula A-2: 99.95% Water, 0.05% Benzene. Heated to 50C in a borosilicate glass beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "APPROVED")

    @patch("src.agents.hardware_agent._mcp_check")
    async def test_benzene_ppm_exceeds_limit(self, mock_mcp, mock_cache):
        mock_mcp.return_value = ({"equipment_name": "polypropylene container", "target_temperature_celsius": 25.0, "max_safe_temperature_celsius": 100.0, "is_safe": True, "status": "SAFE"}, True, True)
        input_text = "Mix 99% Water and 5 ppm Benzene. Store at 25C in a polypropylene container."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    @patch("src.agents.hardware_agent._mcp_check")
    async def test_benzene_ppm_compliant(self, mock_mcp, mock_cache):
        mock_mcp.return_value = ({"equipment_name": "polypropylene container", "target_temperature_celsius": 25.0, "max_safe_temperature_celsius": 100.0, "is_safe": True, "status": "SAFE"}, True, True)
        input_text = "Mix 99.999% Water and 0.5 ppm Benzene. Store at 25C in a polypropylene container."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "APPROVED")

    @patch("src.agents.hardware_agent._mcp_check")
    async def test_acetone_ppm_exceeds_limit(self, mock_mcp, mock_cache):
        mock_mcp.return_value = ({"equipment_name": "polypropylene container", "target_temperature_celsius": 60.0, "max_safe_temperature_celsius": 100.0, "is_safe": True, "status": "SAFE"}, True, True)
        input_text = "Formula B-1: 1500 ppm Acetone in water. Heat to 60C in a polypropylene container."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    @patch("src.agents.hardware_agent._mcp_check")
    async def test_acetone_ppm_boiling_point_hazard(self, mock_mcp, mock_cache):
        mock_mcp.return_value = ({"equipment_name": "polypropylene container", "target_temperature_celsius": 60.0, "max_safe_temperature_celsius": 100.0, "is_safe": True, "status": "SAFE"}, True, True)
        input_text = "Formula B-2: 500 ppm Acetone in water. Heat to 60C in a polypropylene container."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    @patch("src.agents.hardware_agent._mcp_check")
    async def test_hardware_glass_thermal_exceeds(self, mock_mcp, mock_cache):
        mock_mcp.return_value = ({"equipment_name": "soda-lime glass beaker", "target_temperature_celsius": 120.0, "max_safe_temperature_celsius": 100.0, "is_safe": False, "status": "UNSAFE"}, True, True)
        input_text = "Water heating: 100% Water. Heat to 120C in a soda-lime glass beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    @patch("src.agents.hardware_agent._mcp_check")
    async def test_hardware_glass_thermal_compliant(self, mock_mcp, mock_cache):
        mock_mcp.return_value = ({"equipment_name": "soda-lime glass beaker", "target_temperature_celsius": 80.0, "max_safe_temperature_celsius": 100.0, "is_safe": True, "status": "SAFE"}, True, True)
        input_text = "Water heating: 100% Water. Heat to 80C in a soda-lime glass beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "APPROVED")

    async def test_empty_extraction_returns_review_required(self, mock_cache):
        with patch("src.agents.supervisor._extract_entities", new_callable=AsyncMock, return_value=([], [], False)):
            res = await run_supervisor("invalid input text", intent="audit")
            self.assertEqual(res.compliance_report.overall_approval_status, "REVIEW_REQUIRED")
            self.assertIsNone(res.sds_document)


if __name__ == "__main__":
    unittest.main()
