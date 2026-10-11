from odoo.tests import new_test_user, tagged

from .test_common import TestPlmCommon


@tagged("post_install", "-at_install")
class TestBomStructureEcos(TestPlmCommon):
    def test_the_structure_counts_open_ecos_once_for_the_whole_tree(self):
        user = new_test_user(
            self.env,
            login="plm_structure_reader",
            groups="mrp.group_mrp_user,mrp_plm.group_plm_user",
        )
        self._create_eco(
            "Table change", self.bom_table, self.eco_type.id, self.eco_stage.id
        )
        self.env["mrp.eco"].create(
            {
                "name": "Leg change",
                "product_tmpl_id": self.table_leg.product_tmpl_id.id,
                "type_id": self.eco_type.id,
                "stage_id": self.eco_stage.id,
                "type": "product",
            }
        )
        report = self.env["report.mrp.report_bom_structure"].with_user(user)
        self.env.flush_all()
        with self.capturedQueries() as queries:
            lines = report._get_report_data(self.bom_table.id)["lines"]
        self.assertEqual(sum('"mrp_eco"' in query for query in queries), 1)
        self.assertEqual(lines["ecos"], 1)
        ecos = {line["product"]: line["ecos"] for line in lines["components"]}
        self.assertEqual(ecos, {self.table_sheet: "", self.table_leg: 1})
