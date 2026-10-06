from odoo.tests import tagged

from odoo.addons.conversation.tests.test_tools import ConversationToolCase


@tagged("post_install", "-at_install")
class TestMrpTools(ConversationToolCase):
    @classmethod
    def _functional_groups(cls):
        return super()._functional_groups() | cls.env.ref("mrp.group_mrp_manager")

    def _proposal(self, xmlid, payload):
        record = self._recorded()
        return self._propose_tool(self.env.ref(xmlid), payload, record)

    def test_bom_with_missing_component_fails_without_creating_anything(self):
        self.env["product.template"].create({"name": "Mezcla XM 1L"})
        boms_before = self.env["mrp.bom"].search_count([])
        action = self._proposal(
            "conversation_mrp.tool_create_bom",
            {
                "product_name": "Mezcla XM",
                "quantity": 1,
                "components": ["Nada de nada | 2"],
            },
        )
        self._approve(action, self.manager)
        self.assertEqual(action.state, "failed")
        self.assertIn("Nada de nada", action.error)
        self.assertEqual(self.env["mrp.bom"].search_count([]), boms_before)

    def test_manufacturing_order_is_born_draft(self):
        self.env["product.product"].create({"name": "Mezcla XM 200L"})
        action = self._proposal(
            "conversation_mrp.tool_create_manufacturing_order",
            {"product_name": "Mezcla XM 200L", "quantity": 5},
        )
        self._approve(action, self.manager)
        self.assertEqual(action.state, "applied", action.error)
        production = self.env["mrp.production"].browse(action.applied_res_id)
        self.assertEqual(production.state, "draft")
        self.assertEqual(production.product_qty, 5)
