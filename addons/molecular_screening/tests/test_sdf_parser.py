from odoo.tests import BaseCase, tagged

from ..tools.sdf_parser import parse_sdf
from .common import SDF_SAMPLE


@tagged("post_install", "-at_install")
class TestSdfParser(BaseCase):
    def test_records_and_tags(self):
        records = parse_sdf(SDF_SAMPLE)
        self.assertEqual(
            [r["name"] for r in records], ["glifosato", "CHEMBL1", "CHEMBL999"]
        )
        self.assertEqual(records[0]["tags"]["formula"], "C3H8NO5P")
        self.assertEqual(records[2]["tags"]["motivo"], "parecido:glifosato")

    def test_molblock_stops_at_m_end(self):
        molblock = parse_sdf(SDF_SAMPLE)[0]["molblock"]
        self.assertTrue(molblock.endswith("M  END\n"))
        self.assertNotIn("smiles", molblock)

    def test_crlf_and_garbage(self):
        self.assertEqual(len(parse_sdf(SDF_SAMPLE.replace("\n", "\r\n"))), 3)
        self.assertEqual(parse_sdf("not an sdf\n$$$$\n"), [])
