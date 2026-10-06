from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.conversation.tests.test_tools import ConversationToolCase


@tagged("post_install", "-at_install")
class TestSaleTools(ConversationToolCase):
    @classmethod
    def _functional_groups(cls):
        return super()._functional_groups() | cls.env.ref("sale.group_sale_manager")

    def test_medium_risk_is_for_leaders_and_quotation_stays_draft(self):
        product = self.env["product.product"].create(
            {"name": "Zafirex XM 350 EC 1L", "list_price": 6000}
        )
        record = self._recorded()
        action = self._propose_tool(
            self.env.ref("conversation_sale.tool_create_quotation"),
            {"lines": ["Zafirex | 2 | cajas", "Producto inexistente | 1"]},
            record,
        )
        with self.assertRaises((AccessError, UserError)):
            self._approve(action, self.rep)
        self._approve(action, self.leader)
        self.assertEqual(action.state, "applied", action.error)
        order = self.env["sale.order"].browse(action.applied_res_id)
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.partner_id, self.customer)
        products = order.line_ids.filtered("product_id")
        self.assertEqual(products.product_id, product)
        notes = order.line_ids.filtered(lambda l: l.display_type == "line_note")
        self.assertIn("Producto inexistente", notes.name)
