from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProjectMrp(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Assembly line"})
        cls.product = cls.env["product.product"].create(
            {"name": "Finished good", "is_storable": True}
        )
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.product.product_tmpl_id.id,
                "product_qty": 1.0,
                "project_id": cls.project.id,
            }
        )

    def _production(self):
        return self.env["mrp.production"].create(
            {"product_id": self.product.id, "product_qty": 1.0, "bom_id": self.bom.id}
        )

    def test_bom_count_reflects_linked_boms(self):
        self.assertEqual(self.project.bom_count, 1)

    def test_action_view_mrp_bom_is_scoped_to_project(self):
        action = self.project.action_view_mrp_bom()
        self.assertEqual(action["res_model"], "mrp.bom")
        self.assertEqual(action["domain"], [("project_id", "=", self.project.id)])
        self.assertEqual(action["context"]["default_project_id"], self.project.id)

    def test_production_inherits_project_from_bom(self):
        production = self._production()
        self.assertEqual(production.project_id, self.project)
        self.assertEqual(self.project.production_count, 1)

    def test_procurement_project_takes_precedence_over_bom(self):
        project = self.env["project.project"].create({"name": "Customer assembly"})
        self._assert_procurement_project({"project_id": project.id}, project)

    def test_procurement_without_project_uses_bom_project(self):
        self._assert_procurement_project({}, self.project)

    def test_procurement_with_empty_project_uses_bom_project(self):
        self._assert_procurement_project({"project_id": False}, self.project)

    def _assert_procurement_project(self, values, expected_project):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        procurement = self.env["stock.rule"].Procurement(
            self.product,
            1.0,
            self.product.uom_id,
            warehouse.lot_stock_id,
            "Project assembly",
            "Project assembly",
            warehouse.company_id,
            {
                "warehouse_id": warehouse,
                "date_planned": fields.Datetime.now(),
                "company_id": warehouse.company_id,
                **values,
            },
        )
        self.env["stock.rule"]._run_manufacture(
            [(procurement, warehouse.manufacture_pull_id)]
        )
        production = self.env["mrp.production"].search(
            [("product_id", "=", self.product.id)]
        )
        self.assertEqual(len(production), 1)
        self.assertEqual(production.project_id, expected_project)

    def test_action_view_project_targets_the_project(self):
        production = self._production()
        action = production.action_view_project()
        self.assertEqual(action["res_model"], "project.project")
        self.assertEqual(action["res_id"], self.project.id)

    def test_action_view_mrp_production_is_scoped_to_project(self):
        action = self.project.action_view_mrp_production()
        self.assertEqual(action["res_model"], "mrp.production")
        self.assertEqual(action["domain"], [("project_id", "=", self.project.id)])
        self.assertEqual(action["context"]["default_project_id"], self.project.id)
        self.assertTrue(action["context"]["from_project_action"])

    def test_stat_buttons_include_mrp_entries(self):
        buttons = {
            b["action"]: b for b in self.project._get_stat_buttons() if "action" in b
        }
        self.assertIn("action_view_mrp_bom", buttons)
        self.assertIn("action_view_mrp_production", buttons)
        self.assertEqual(
            buttons["action_view_mrp_bom"]["number"], self.project.bom_count
        )
