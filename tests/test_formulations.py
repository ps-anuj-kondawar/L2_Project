import unittest
import asyncio
from src.agents.supervisor import run_supervisor

class TestFormulationCompliance(unittest.IsolatedAsyncioTestCase):

    async def test_benzene_volume_exceeds_limit(self):

        input_text = "Formula A-1: 94% Water, 6% Benzene. Heated to 50C in a borosilicate glass beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    async def test_benzene_volume_compliant(self):

        input_text = "Formula A-2: 99.95% Water, 0.05% Benzene. Heated to 50C in a borosilicate glass beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "APPROVED")

    async def test_benzene_ppm_exceeds_limit(self):

        input_text = "Mix 99% Water and 5 ppm Benzene. Store at 25C in a polypropylene container."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    async def test_benzene_ppm_compliant(self):

        input_text = "Mix 99.999% Water and 0.5 ppm Benzene. Store at 25C in a polypropylene container."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "APPROVED")

    async def test_acetone_ppm_exceeds_limit(self):

        input_text = "Formula B-1: 1500 ppm Acetone in water. Heat to 60C in a polypropylene container."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    async def test_acetone_ppm_boiling_point_hazard(self):

        input_text = "Formula B-2: 500 ppm Acetone in water. Heat to 60C in a polypropylene container."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "PARTIAL")

    async def test_toluene_ppm_exceeds_limit(self):

        input_text = "Note: Contains 300 ppm Toluene. Store at 25C in a stainless steel beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    async def test_toluene_ppm_compliant(self):

        input_text = "Note: Contains 150 ppm Toluene. Store at 25C in a stainless steel beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "APPROVED")

    async def test_hardware_glass_thermal_exceeds(self):

        input_text = "Water heating: 100% Water. Heat to 120C in a soda-lime glass beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "REJECTED")

    async def test_hardware_glass_thermal_compliant(self):

        input_text = "Water heating: 100% Water. Heat to 80C in a soda-lime glass beaker."
        res = await run_supervisor(input_text, intent="audit")
        self.assertEqual(res.compliance_report.overall_approval_status, "APPROVED")


if __name__ == "__main__":
    unittest.main()
