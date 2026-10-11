from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.conversation.tests.test_tools import ConversationToolCase


@tagged("post_install", "-at_install")
class TestPurchaseTool(ConversationToolCase):
    @classmethod
    def _functional_groups(cls):
        return super()._functional_groups() | cls.env.ref(
            "purchase.group_purchase_user"
        )

    def test_supplier_call_proposes_a_draft_rfq(self):
        product = self.env["product.product"].create({"name": "Glifosato 480 SL 20L"})
        supplier = self.env["res.partner"].create(
            {"name": "Agroinsumos del Valle", "is_company": True}
        )
        record = self._recorded(partner_id=supplier.id)
        tool = self.env.ref("conversation_purchase.tool_create_purchase_order")
        action = self._propose_tool(
            tool,
            {
                "lines": ["Glifosato 480 | 20 | tambos"],
                "date_planned": "2026-09-30",
            },
            record,
        )
        with self.assertRaises((AccessError, UserError)):
            self._approve(action, self.rep)
        self._approve(action, self.leader)
        self.assertEqual(action.state, "applied", action.error)
        order = self.env["purchase.order"].browse(action.applied_res_id)
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.partner_id, supplier)
        self.assertEqual(order.line_ids.product_id, product)
        self.assertEqual(order.line_ids.product_qty, 20)

    def test_unknown_product_fails_instead_of_guessing(self):
        supplier = self.env["res.partner"].create({"name": "Proveedor X"})
        record = self._recorded(partner_id=supplier.id)
        tool = self.env.ref("conversation_purchase.tool_create_purchase_order")
        action = self._propose_tool(tool, {"lines": ["Nada | 1"]}, record)
        self._approve(action, self.manager)
        self.assertEqual(action.state, "failed")
        self.assertIn("Nada", action.error)
