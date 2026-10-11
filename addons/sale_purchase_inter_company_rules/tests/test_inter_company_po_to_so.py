from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import TestInterCompanyRulesCommonSOPO


@tagged("post_install", "-at_install")
class TestInterCompanyPurchaseToSale(TestInterCompanyRulesCommonSOPO):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env["res.currency"]._activate_group_multi_currency()

    def _generate_draft_purchase_order(self, company, partner):
        purchase_order = Form(self.env["purchase.order"])
        purchase_order.partner_id = partner
        purchase_order.company_id = company
        purchase_order = purchase_order.save()

        with Form(purchase_order) as po:
            with po.line_ids.new() as line:
                line.name = "Service"
                line.product_id = self.product_consultant
                line.price_unit = 450.0
                line.discount = 10.0

        return purchase_order

    def generate_purchase_order(self, company, partner):
        purchase_order = self._generate_draft_purchase_order(company, partner)
        purchase_order.action_confirm()
        self.assertEqual(
            purchase_order.state, "done", "Purchase order should be in purchase state."
        )
        return purchase_order

    def validate_generated_sale_order(self, purchase_order, company, partner):

        sale_order = (
            self.env["sale.order"]
            .with_company(partner)
            .search([("client_order_ref", "=", purchase_order.name)], limit=1)
        )
        fp = (
            self.env["account.fiscal.position"]
            .with_company(partner)
            ._get_fiscal_position(company.partner_id)
        )

        self.assertEqual(
            sale_order.state, "draft", "sale order should be in draft state."
        )
        self.assertEqual(
            sale_order.partner_id,
            company.partner_id,
            "Vendor does not correspond to Company %s." % company,
        )
        self.assertEqual(
            sale_order.company_id,
            partner,
            "Applied company in created sale order is incorrect.",
        )
        self.assertEqual(sale_order.amount_total, 465.75, "Total amount is incorrect.")
        self.assertEqual(
            sale_order.line_ids[0].product_id,
            self.product_consultant,
            "Product in line is incorrect.",
        )
        self.assertEqual(
            sale_order.line_ids[0].name, "Service", "Product name is incorrect."
        )
        self.assertEqual(
            sale_order.line_ids[0].product_qty, 1, "Product qty is incorrect."
        )
        self.assertEqual(
            sale_order.line_ids[0].price_unit, 450, "Unit Price in line is incorrect."
        )
        self.assertEqual(
            sale_order.line_ids[0].price_subtotal, 405, "Subtotal in line is incorrect."
        )
        self.assertEqual(sale_order.fiscal_position_id, fp)

    def test_00_inter_company_sale_purchase(self):

        self.company_b.update(
            {
                "intercompany_generate_sales_orders": True,
                "intercompany_generate_purchase_orders": True,
            }
        )
        purchase_order = self.generate_purchase_order(
            self.company_a, self.company_b.partner_id
        )
        self.validate_generated_sale_order(
            purchase_order, self.company_a, self.company_b
        )
        self.company_b.update(
            {
                "intercompany_generate_sales_orders": False,
                "intercompany_generate_purchase_orders": False,
            }
        )

        self.company_a.update(
            {
                "intercompany_generate_sales_orders": True,
                "intercompany_generate_purchase_orders": True,
            }
        )
        purchase_order = self.generate_purchase_order(
            self.company_b, self.company_a.partner_id
        )
        self.validate_generated_sale_order(
            purchase_order, self.company_b, self.company_a
        )
        self.company_a.update(
            {
                "intercompany_generate_sales_orders": False,
                "intercompany_generate_purchase_orders": False,
            }
        )

    def test_01_inter_company_purchase_order_with_configuration(self):

        self.company_b.update(
            {
                "intercompany_generate_sales_orders": True,
            }
        )
        purchase_order = self.generate_purchase_order(
            self.company_a, self.company_b.partner_id
        )
        self.validate_generated_sale_order(
            purchase_order, self.company_a, self.company_b
        )
        self.company_b.update(
            {
                "intercompany_generate_sales_orders": False,
            }
        )

        self.company_a.update(
            {
                "intercompany_generate_sales_orders": True,
            }
        )
        purchase_order = self.generate_purchase_order(
            self.company_b, self.company_a.partner_id
        )
        self.validate_generated_sale_order(
            purchase_order, self.company_b, self.company_a
        )
        self.company_a.update(
            {
                "intercompany_generate_sales_orders": False,
            }
        )

    def test_02_inter_company_purchase_order_without_configuration(self):

        purchase_order = self.generate_purchase_order(
            self.company_a, self.company_b.partner_id
        )
        sale_order = self.env["sale.order"].search(
            [("client_order_ref", "=", purchase_order.name)], limit=1
        )
        self.assertTrue(
            (not sale_order),
            "Sale order created for company B from Purchase order of company A without configuration",
        )

        purchase_order = self.generate_purchase_order(
            self.company_b, self.company_a.partner_id
        )
        sale_order = self.env["sale.order"].search(
            [("client_order_ref", "=", purchase_order.name)], limit=1
        )
        self.assertTrue(
            (not sale_order),
            "Sale order created for company A from Purchase order of company B without configuration",
        )

    def test_06_inter_company_purchase_order_from_so_with_sales_team(self):
        self.company_b.update(
            {
                "intercompany_generate_sales_orders": True,
            }
        )
        self.env["team.team"].search([]).action_archive()
        self.env["team.team"].create(
            {
                "use_sale": True,
                "name": "Team A",
                "company_id": self.company_a.id,
            }
        )
        purchase_order = self.generate_purchase_order(
            self.company_a, self.company_b.partner_id
        )
        sale_order = (
            self.env["sale.order"]
            .with_company(self.company_b)
            .search([("client_order_ref", "=", purchase_order.name)], limit=1)
        )
        self.assertRecordValues(
            sale_order,
            [
                {
                    "company_id": self.company_b.id,
                    "team_id": False,
                }
            ],
        )
        valid_sales_team = self.env["team.team"].create(
            {
                "use_sale": True,
                "name": "Team B",
                "company_id": self.company_b.id,
            }
        )
        purchase_order_2 = self.generate_purchase_order(
            self.company_a, self.company_b.partner_id
        )
        sale_order = (
            self.env["sale.order"]
            .with_company(self.company_b)
            .search([("client_order_ref", "=", purchase_order_2.name)], limit=1)
        )
        self.assertRecordValues(
            sale_order,
            [
                {
                    "company_id": self.company_b.id,
                    "team_id": valid_sales_team.id,
                }
            ],
        )

    def test_07_no_intercompany_user_raises_clear_error(self):
        self.company_b.intercompany_user_id = False
        purchase_order = self._generate_draft_purchase_order(
            self.company_a, self.company_b.partner_id
        )
        with self.assertRaises(UserError):
            purchase_order.inter_company_create_sale_order(self.company_b)

    def test_08_access_rights_checked_against_intercompany_user_not_caller(self):
        unprivileged_user = self._create_unprivileged_user(
            "unprivileged_intercompany_po_so", self.company_b
        )
        self.company_b.intercompany_user_id = unprivileged_user.id
        purchase_order = self._generate_draft_purchase_order(
            self.company_a, self.company_b.partner_id
        )
        with self.assertRaises(UserError):
            purchase_order.inter_company_create_sale_order(self.company_b)

    def test_09_reconfirm_does_not_duplicate_sale_order(self):
        self.company_b.update(
            {
                "intercompany_generate_sales_orders": True,
            }
        )
        purchase_order = self._generate_draft_purchase_order(
            self.company_a, self.company_b.partner_id
        )
        purchase_order.action_confirm()
        sale_orders = self.env["sale.order"].search(
            [("company_id", "=", self.company_b.id)]
        )
        self.assertEqual(len(sale_orders), 1)

        purchase_order.action_cancel()
        purchase_order.action_draft()
        purchase_order.action_confirm()

        sale_orders = self.env["sale.order"].search(
            [
                ("company_id", "=", self.company_b.id),
                ("state", "!=", "cancel"),
            ]
        )
        self.assertEqual(
            len(sale_orders),
            1,
            "Re-confirming the PO must not create a second, non-cancelled SO",
        )
