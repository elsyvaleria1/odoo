from odoo.tests import tagged

from .common import TestFsmFlowSaleCommon


@tagged("post_install", "-at_install")
class TestFsmQuantitySearch(TestFsmFlowSaleCommon):
    def test_a_quantity_is_found_by_equality_as_well_as_by_bound(self):
        product = self.env["product.product"].create(
            {"name": "Material", "type": "consu", "list_price": 10}
        )
        self.task.write({"partner_id": self.partner_1.id})
        self.task.with_user(self.project_user).action_fsm_view_material()
        products = self.env["product.product"].with_context(fsm_task_id=self.task.id)
        products.browse(product.id).set_fsm_quantity(3)
        for domain in (
            [("fsm_quantity", "=", 3)],
            [("fsm_quantity", "in", [3, 4])],
            [("fsm_quantity", ">", 0)],
        ):
            with self.subTest(domain=domain):
                self.assertEqual(
                    products.search([*domain, ("id", "=", product.id)]), product
                )
        self.assertFalse(
            products.search([("fsm_quantity", "=", 2), ("id", "=", product.id)])
        )
