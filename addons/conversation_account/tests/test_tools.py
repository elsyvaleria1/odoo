from odoo.tests import tagged

from odoo.addons.conversation.tests.test_tools import ConversationToolCase


@tagged("post_install", "-at_install")
class TestAccountTools(ConversationToolCase):
    @classmethod
    def _functional_groups(cls):
        return super()._functional_groups() | cls.env.ref(
            "account.group_account_invoice"
        )

    def _ensure_sale_journal(self, partner):
        if self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.company.id)], limit=1
        ):
            return
        income = self.env["account.account"].create(
            {"name": "Ingresos (test)", "code": "TEST400", "account_type": "income"}
        )
        self.env["account.journal"].create(
            {
                "name": "Ventas (test)",
                "type": "sale",
                "code": "TINV",
                "company_id": self.company.id,
                "default_account_id": income.id,
            }
        )
        receivable = self.env["account.account"].create(
            {
                "name": "Clientes (test)",
                "code": "TEST105",
                "account_type": "asset_receivable",
                "reconcile": True,
            }
        )
        partner.property_account_receivable_id = receivable

    def test_draft_invoice_with_priced_lines(self):
        product = self.env["product.product"].create(
            {"name": "Servicio de aplicación", "list_price": 1500}
        )
        record = self._recorded()
        self._ensure_sale_journal(record.partner_id)
        action = self._propose_tool(
            self.env.ref("conversation_account.tool_create_invoice_draft"),
            {
                "lines": [
                    "Servicio de aplicación | 2 | 1500",
                    "Concepto libre | 1 | 300",
                ]
            },
            record,
        )
        self._approve(action, self.manager)
        self.assertEqual(action.state, "applied", action.error)
        move = self.env["account.move"].browse(action.applied_res_id)
        self.assertEqual(move.state, "draft")
        self.assertEqual(move.move_type, "out_invoice")
        self.assertEqual(len(move.invoice_line_ids), 2)
        self.assertIn(product, move.invoice_line_ids.product_id)
        priced = move.invoice_line_ids.filtered(lambda l: l.name == "Concepto libre")
        self.assertEqual(priced.price_unit, 300)
