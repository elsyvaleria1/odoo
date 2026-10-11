from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import TestInterCompanyRulesCommonSOPO


@tagged("post_install", "-at_install")
class TestInterCompanySaleToPurchase(TestInterCompanyRulesCommonSOPO):
    def _generate_draft_sale_order(self, company, partner, user):
        sale_order = Form(self.env["sale.order"])
        sale_order.company_id = company
        sale_order.partner_id = partner
        sale_order.user_id = user
        with sale_order.line_ids.new() as line:
            line.name = "Service"
            line.product_id = self.product_consultant
            line.price_unit = 450.0
            line.discount = 10.0

        return sale_order.save()

    def generate_sale_order(self, company, partner, user):
        sale_order = self._generate_draft_sale_order(company, partner, user)
        sale_order.action_confirm()

    def validate_generated_purchase_order(self, company, partner):

        purchase_order = self.env["purchase.order"].search(
            [("company_id", "=", partner.id)], limit=1
        )
        fp = (
            self.env["account.fiscal.position"]
            .with_company(partner)
            ._get_fiscal_position(company.partner_id)
        )

        self.assertEqual(
            purchase_order.state, "draft", "Invoice should be in draft state."
        )
        self.assertEqual(
            purchase_order.partner_id,
            company.partner_id,
            "Vendor does not correspond to Company %s." % company.name,
        )
        self.assertEqual(
            purchase_order.company_id,
            partner,
            "Company is not correspond to purchase order.",
        )
        self.assertEqual(
            purchase_order.amount_total, 465.75, "Total amount is incorrect."
        )
        self.assertEqual(
            purchase_order.line_ids[0].product_id,
            self.product_consultant,
            "Product in line is incorrect.",
        )
        self.assertEqual(
            purchase_order.line_ids[0].name, "Service", "Product name is incorrect."
        )
        self.assertEqual(
            purchase_order.line_ids[0].price_unit, 450, "Price unit is incorrect."
        )
        self.assertEqual(
            purchase_order.line_ids[0].product_qty, 1, "Product qty is incorrect."
        )
        self.assertEqual(
            purchase_order.line_ids[0].price_subtotal, 405, "line total is incorrect."
        )
        self.assertEqual(purchase_order.fiscal_position_id, fp)
        return purchase_order

    def test_00_inter_company_sale_purchase(self):

        self.company_b.update(
            {
                "intercompany_generate_sales_orders": True,
                "intercompany_generate_purchase_orders": True,
            }
        )
        self.generate_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        self.validate_generated_purchase_order(self.company_a, self.company_b)
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
        self.generate_sale_order(
            self.company_b, self.company_a.partner_id, self.res_users_company_b
        )
        self.validate_generated_purchase_order(self.company_b, self.company_a)
        self.company_a.update(
            {
                "intercompany_generate_sales_orders": False,
                "intercompany_generate_purchase_orders": False,
            }
        )

    def test_01_inter_company_sale_order_with_configuration(self):

        self.company_b.update(
            {
                "intercompany_generate_purchase_orders": True,
            }
        )
        self.generate_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        self.validate_generated_purchase_order(self.company_a, self.company_b)
        self.company_b.update(
            {
                "intercompany_generate_purchase_orders": False,
            }
        )

        self.company_a.update(
            {
                "intercompany_generate_purchase_orders": True,
            }
        )
        self.generate_sale_order(
            self.company_b, self.company_a.partner_id, self.res_users_company_b
        )
        self.validate_generated_purchase_order(self.company_b, self.company_a)
        self.company_a.update(
            {
                "intercompany_generate_purchase_orders": False,
            }
        )

    def test_02_sale_to_purchase_without_configuration(self):

        self.generate_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        purchase_order = self.env["purchase.order"].search(
            [("company_id", "=", self.company_b.id)], limit=1
        )
        self.assertTrue(
            (not purchase_order),
            "Purchase order created for company A from Purchase order of company B without configuration",
        )

        self.generate_sale_order(
            self.company_b, self.company_a.partner_id, self.res_users_company_b
        )
        purchase_order = self.env["purchase.order"].search(
            [("company_id", "=", self.company_a.id)], limit=1
        )
        self.assertTrue(
            (not purchase_order),
            "Sale order created for company B from Purchase order of company B without configuration",
        )

    def test_03_inter_company_so_section(self):

        self.company_b.update(
            {
                "intercompany_generate_sales_orders": True,
                "intercompany_generate_purchase_orders": True,
            }
        )
        so = self._generate_draft_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        so.write(
            {
                "line_ids": [
                    (
                        0,
                        False,
                        {"display_type": "line_section", "name": "Great Section"},
                    )
                ]
            }
        )
        so.action_confirm()
        self.assertEqual(len(so.line_ids), 2)
        po = self.validate_generated_purchase_order(self.company_a, self.company_b)
        self.assertEqual(len(po.line_ids), 2)

    def test_04_inter_company_auto_validation(self):
        my_service = self.env["product.product"].create(
            {
                "name": "my service",
                "type": "service",
                "service_to_purchase": True,
                "seller_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.company_b.partner_id.id,
                            "price": 100,
                            "company_id": self.company_a.id,
                        },
                    )
                ],
            }
        )

        self.company_b.update(
            {
                "intercompany_generate_sales_orders": True,
                "intercompany_generate_purchase_orders": True,
                "intercompany_document_state": "posted",
            }
        )
        partner_a = self.env["res.partner"].create(
            {
                "name": "partner_a",
                "company_id": False,
            }
        )
        so = self._generate_draft_sale_order(
            self.company_a, partner_a, self.res_users_company_a
        )
        so.line_ids.product_id = my_service
        so.line_ids.product_uom_id = my_service.uom_id
        so.with_user(self.res_users_company_a).action_confirm()
        purchase_order = self.env["purchase.order"].search(
            [("partner_id", "=", self.company_b.partner_id.id)], limit=1
        )
        self.assertTrue(purchase_order)
        purchase_order.with_user(self.res_users_company_a).action_confirm()

    def test_05_inter_company_delivery_date(self):
        today = fields.Datetime.today()
        self.company_b.update(
            {
                "intercompany_generate_purchase_orders": True,
            }
        )

        sale_order = self._generate_draft_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        sale_order.date_commitment = today + relativedelta(days=7)
        sale_order.with_user(self.res_users_company_a).action_confirm()

        purchase_order = self.env["purchase.order"].search(
            [("company_id", "=", self.company_b.id)], limit=1
        )
        self.assertEqual(purchase_order.date_commitment, today + relativedelta(days=7))

    def test_sale_to_specific_partner(self):
        self.company_b.update(
            {
                "intercompany_generate_sales_orders": True,
                "intercompany_generate_purchase_orders": True,
            }
        )
        partner_b = self.env["res.partner"].create(
            {
                "name": "SuperPartner",
                "parent_id": self.company_b.partner_id.id,
            }
        )
        so = self._generate_draft_sale_order(
            self.company_a, partner_b, self.res_users_company_a
        )
        so.with_user(self.res_users_company_a).action_confirm()
        purchase_order = (
            self.env["purchase.order"]
            .sudo()
            .search([("partner_id", "=", self.company_a.partner_id.id)], limit=1)
        )
        self.assertEqual(purchase_order.company_id, self.company_b)

    def test_inter_company_auto_validation(self):
        buyer, vendor = self.env["res.partner"].create(
            [
                {
                    "name": "buyer",
                    "company_id": False,
                },
                {
                    "name": "vendor",
                    "company_id": False,
                },
            ]
        )

        (self.company_a | self.company_b).update(
            {
                "intercompany_generate_sales_orders": True,
                "intercompany_generate_purchase_orders": True,
                "intercompany_document_state": "posted",
            }
        )

        service_purchase = self.env["product.product"].create(
            {
                "name": "service 1",
                "purchase_ok": True,
                "sale_ok": True,
                "type": "service",
                "service_to_purchase": True,
                "seller_ids": [
                    Command.create(
                        {
                            "partner_id": self.company_b.partner_id.id,
                            "price": 100,
                            "company_id": self.company_a.id,
                        }
                    ),
                    Command.create(
                        {
                            "partner_id": vendor.id,
                            "price": 100,
                            "company_id": self.company_b.id,
                        }
                    ),
                ],
            }
        )
        service_purchase.with_company(self.company_b).update(
            {"service_to_purchase": True}
        )

        so_a = self._generate_draft_sale_order(
            self.company_a, buyer, self.res_users_company_a
        )
        so_a.line_ids.product_id = service_purchase
        so_a.with_company(self.company_a).action_confirm()

        po_a = so_a._get_purchase_orders()
        self.assertEqual(po_a.company_id, self.company_a)
        self.assertEqual(po_a.partner_id, self.company_b.partner_id)
        self.assertEqual(po_a.line_ids.product_id, service_purchase)

        po_a.with_company(self.company_a).action_confirm()
        so_b = (
            self.env["sale.order"]
            .with_company(self.company_b)
            .search([("partner_id", "=", self.company_a.partner_id.id)], limit=1)
        )
        self.assertEqual(so_b.company_id, self.company_b)
        self.assertEqual(so_b.partner_id, self.company_a.partner_id)
        self.assertEqual(so_b.line_ids.product_id, service_purchase)

        po_b = so_b._get_purchase_orders()
        self.assertEqual(po_b.company_id, self.company_b)
        self.assertEqual(po_b.partner_id, vendor)
        self.assertEqual(po_b.line_ids.product_id, service_purchase)

    def test_07_reconfirm_does_not_duplicate_purchase_order(self):
        self.company_b.update(
            {
                "intercompany_generate_purchase_orders": True,
            }
        )
        so = self._generate_draft_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        so.with_user(self.res_users_company_a).action_confirm()
        purchase_orders = self.env["purchase.order"].search(
            [("company_id", "=", self.company_b.id)]
        )
        self.assertEqual(len(purchase_orders), 1)

        so.action_cancel()
        so.action_draft()
        so.with_user(self.res_users_company_a).action_confirm()

        purchase_orders = self.env["purchase.order"].search(
            [
                ("company_id", "=", self.company_b.id),
                ("state", "!=", "cancel"),
            ]
        )
        self.assertEqual(
            len(purchase_orders),
            1,
            "Re-confirming the SO must not create a second, non-cancelled PO",
        )

    def test_08_currency_mismatch_blocks_purchase_order_generation(self):
        self.company_b.update(
            {
                "intercompany_generate_purchase_orders": True,
            }
        )
        eur = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "=", "EUR")], limit=1)
        )
        eur.active = True
        self.assertNotEqual(eur, self.company_a.currency_id)
        self.company_a.partner_id.with_company(
            self.company_b
        ).property_purchase_currency_id = eur

        so = self._generate_draft_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        with self.assertRaises(UserError):
            so.with_user(self.res_users_company_a).action_confirm()

    def test_09_no_intercompany_user_raises_clear_error(self):
        self.company_b.update(
            {
                "intercompany_generate_purchase_orders": True,
                "intercompany_user_id": False,
            }
        )
        so = self._generate_draft_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        with self.assertRaises(UserError):
            so.with_user(self.res_users_company_a).action_confirm()

    def test_10_access_rights_checked_against_intercompany_user_not_caller(self):
        unprivileged_user = self._create_unprivileged_user(
            "unprivileged_intercompany_so_po", self.company_b
        )
        self.company_b.update(
            {
                "intercompany_generate_purchase_orders": True,
                "intercompany_user_id": unprivileged_user.id,
            }
        )
        so = self._generate_draft_sale_order(
            self.company_a, self.company_b.partner_id, self.res_users_company_a
        )
        with self.assertRaises(UserError):
            so.with_user(self.res_users_company_a).action_confirm()
