import unittest
import asyncio
from src.agents.supervisor import run_supervisor
from src.infrastructure.pubchem_client import get_pubchem_data


class TestSDSGeneration(unittest.IsolatedAsyncioTestCase):

    async def test_pubchem_client_benzene(self):
        data = await get_pubchem_data("benzene")
        self.assertIsNotNone(data.cid)
        self.assertEqual(data.cas_number, "71-43-2")
        self.assertIn("GHS02", data.ghs_pictogram_codes)
        self.assertEqual(data.signal_word, "DANGER")

    async def test_sds_generation_full_pipeline(self):
        input_text = "Formula A-1: 94% Water, 6% Benzene. Heated to 50C in a borosilicate glass beaker."
        result = await run_supervisor(input_text, intent="full")
        self.assertIsNotNone(result.sds_document)
        self.assertEqual(len(result.sds_document.sections), 16)
        self.assertIsNotNone(result.sds_html)
        self.assertIn("Safety Data Sheet", result.sds_html)
        self.assertGreater(len(result.trace), 0)


if __name__ == "__main__":
    unittest.main()
