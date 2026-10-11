from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import Form, freeze_time, tagged
from odoo.tools import format_date
from odoo.tools.date_utils import get_timedelta
from odoo.tools.misc import NON_BREAKING_SPACE

from odoo.addons.partner_commission.tests.setup import Line, Spec, TestCommissionsSetup


@tagged("commission_purchase", "post_install", "-at_install")
class TestPurchaseOrder(TestCommissionsSetup):
    def test_automatic_confirm(self):
        self.company.commission_automatic_po_frequency = "weekly"
        self.referrer.grade_id = self.learning
        self.referrer._onchange_grade_id()

        send_mail_count = 0

        def make_po(days_offset=0, qty=1):
            inv = self.purchase(Spec(self.gold, [Line(self.crm, qty)]))
            po = inv.commission_po_line_id.order_id
            po.date_order = fields.Date.add(fields.Date.today(), days=days_offset)
            return po

        today_date = fields.Date.to_date("2020-01-06")

        def _patched_send_mail(*args, **kwargs):
            nonlocal send_mail_count
            send_mail_count += 1

        with freeze_time(today_date), self.sync_env_with_side_cursors():
            with patch(
                "odoo.addons.mail.models.mail_template.MailTemplate.send_mail",
                _patched_send_mail,
            ):
                self.crm.recurring_invoice = False
                po = make_po(days_offset=-1)
                self.env.ref(
                    "partner_commission.cron_confirm_purchase_orders"
                ).method_direct_trigger()
                self.assertEqual(po.state, "done")
                self.assertEqual(send_mail_count, 1)

        with freeze_time(today_date), self.sync_env_with_side_cursors():
            po = self.env["purchase.order"].create(
                {
                    "partner_id": self.customer.id,
                    "company_id": self.company.id,
                    "currency_id": self.company.currency_id.id,
                    "date_order": fields.Date.subtract(fields.Date.today(), days=1),
                }
            )
            self.env.ref(
                "partner_commission.cron_confirm_purchase_orders"
            ).method_direct_trigger()
            self.assertEqual(po.state, "draft")

        self.company.commission_po_minimum = 50
        with freeze_time(today_date), self.sync_env_with_side_cursors():
            po = make_po(days_offset=-1, qty=20)
            self.env.ref(
                "partner_commission.cron_confirm_purchase_orders"
            ).method_direct_trigger()
            self.assertEqual(po.state, "done")

        with freeze_time(today_date), self.sync_env_with_side_cursors():
            po = make_po(days_offset=-1, qty=2)
            self.env.ref(
                "partner_commission.cron_confirm_purchase_orders"
            ).method_direct_trigger()
            self.assertEqual(po.state, "draft")

    def test_vendor_bill_description_multi_line_format(self):
        self.salesman.group_ids += self.env.ref(
            "account.group_delivery_invoice_address"
        )
        self.referrer.commission_plan_id = self.gold_plan
        self.referrer.grade_id = self.gold

        form = Form(
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_context(tracking_disable=True),
            view=self.env.ref("sale_subscription.sale_subscription_primary_form_view"),
        )
        form.partner_id = self.customer
        form.partner_invoice_id = self.customer
        form.partner_shipping_id = self.customer
        form.referrer_id = self.referrer
        form.plan_id = self.plan_year

        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 20

        with form.line_ids.new() as line:
            line.display_type = "line_note"
            line.name = "Extra order note for the customer"

        so = form.save()
        so.pricelist_id = self.eur_20
        so.action_confirm()
        inv = so._create_invoices()
        inv.action_post()
        inv.name = "INV/12345/0001"
        self._pay_invoice(inv)
        date_from = fields.Date.today()
        date_to = date_from + get_timedelta(1, "year") - relativedelta(days=1)

        expected = f"""Commission on INV/12345/0001, Customer, 2,000.00{NON_BREAKING_SPACE}€\n{so.name}, \nOdoo.sh Worker: from {format_date(self.env, date_from)} to {format_date(self.env, date_to)} (12 month(s))"""
        self.assertEqual(inv.commission_po_line_id.name, expected)

    def test_purchase_representative(self):
        self.referrer.commission_plan_id = self.gold_plan
        self.referrer.grade_id = self.gold

        def make_orders(product, so_sales_rep=None, sub_sales_rep=None):
            form = Form(
                self.env["sale.order"]
                .with_user(self.salesman)
                .with_context(tracking_disable=True)
            )
            form.partner_id = self.customer
            form.referrer_id = self.referrer
            if so_sales_rep:
                form.user_id = so_sales_rep

            with form.line_ids.new() as line:
                line.name = product.name
                line.product_id = product
                line.product_qty = 1

            so = form.save()
            so.action_confirm()

            inv = so._create_invoices()
            inv.action_post()

            if so and sub_sales_rep:
                so.sudo().user_id = sub_sales_rep

            self._pay_invoice(inv)

            po = inv.commission_po_line_id.order_id

            return so, po

        with self.subTest("No buyer is assigned to the PO."):
            foo = self.env["product.category"].create(
                {
                    "name": "foo",
                }
            )
            bar = self.env["product.product"].create(
                {
                    "name": "bar",
                    "categ_id": foo.id,
                    "list_price": 100.0,
                    "purchase_ok": True,
                    "property_account_income_id": self.account_sale.id,
                    "invoice_policy": "ordered",
                }
            )
            self.env["product.pricelist.item"].create(
                {
                    "plan_id": self.plan_month.id,
                    "price": 20,
                    "product_tmpl_id": bar.product_tmpl_id.id,
                }
            )
            rule = self.env["commission.rule"].create(
                {
                    "plan_id": self.gold_plan.id,
                    "category_id": foo.id,
                    "product_id": bar.id,
                    "rate": 10.0,
                }
            )
            self.gold_plan.write({"commission_rule_ids": [(4, rule.id)]})

            so, first_po = make_orders(bar)

            self.assertEqual(so.user_id, self.salesman)
            self.assertFalse(first_po.user_id)
            self.assertIn(
                self.salesman.partner_id,
                first_po.message_follower_ids.partner_id,
                "Salesman should be follower so he can access the PO.",
            )

        with self.subTest(
            "POs to the same partner are grouped together, even if they come from SOs with different sales representatives."
        ):
            sales_rep = self.env["res.users"].create(
                {
                    "name": "...",
                    "login": "sales_rep_1",
                    "email": "sales_rep_1@odoo.com",
                    "company_id": self.company.id,
                    "group_ids": [(6, 0, [self.ref("sale.group_sale_salesman")])],
                }
            )

            so, second_po = make_orders(bar, so_sales_rep=sales_rep)

            self.assertEqual(so.user_id, sales_rep)
            self.assertFalse(second_po.user_id)
            self.assertEqual(first_po, second_po)
            self.assertIn(
                sales_rep.partner_id,
                first_po.message_follower_ids.partner_id,
                "Salesman should be follower so he can access the PO.",
            )

    def test_access_rigths(self):

        def user(name, group):
            return self.env["res.users"].create(
                {
                    "name": name,
                    "login": name,
                    "email": f"{name}@example.com",
                    "company_id": self.company.id,
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                group,
                            ],
                        )
                    ],
                }
            )

        salesman_own_docs = user(
            "salesman_own_docs", self.ref("sale.group_sale_salesman")
        )
        salesman_all_docs = user(
            "salesman_all_docs", self.ref("sale.group_sale_salesman_all_leads")
        )
        commission_user_1 = user(
            "commission_user_1", self.ref("partner_commission.group_commission_user")
        )
        commission_user_2 = user(
            "commission_user_2", self.ref("partner_commission.group_commission_user")
        )
        commission_manager = user(
            "commission_manager",
            self.ref("partner_commission.group_commission_manager"),
        )
        purchase_user_own_docs = user(
            "purchase_user_own_docs", self.ref("purchase.group_purchase_user")
        )
        purchase_user = user(
            "purchase_user", self.ref("purchase.group_purchase_user_all")
        )

        po = self.env["purchase.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "currency_id": self.company.currency_id.id,
                "date_order": fields.Date.today(),
                "user_id": commission_user_1.id,
            }
        )

        def assert_access_denied(users):
            for usr in users:
                with self.assertRaises(
                    AccessError, msg=f"{usr.name} should be denied access."
                ):
                    Form(po.with_user(usr))

        def assert_access_allowed(users):
            for usr in users:
                Form(po.with_user(usr))

        self.assertTrue(commission_user_1.has_group("sale.group_sale_salesman"))

        self.assertTrue(
            commission_manager.has_group("partner_commission.group_commission_user")
        )

        assert_access_allowed([purchase_user])
        assert_access_denied(
            [
                salesman_own_docs,
                salesman_all_docs,
                commission_user_1,
                commission_manager,
                purchase_user_own_docs,
            ]
        )

        po.purchase_type = "commission"

        assert_access_allowed([purchase_user])

        assert_access_denied([commission_user_2])

        assert_access_allowed([commission_user_1, commission_manager])

        po.message_subscribe(partner_ids=commission_user_2.partner_id.ids)
        assert_access_allowed([commission_user_2])
