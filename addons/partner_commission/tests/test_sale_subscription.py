from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import Form, tagged

from odoo.addons.partner_commission.tests.setup import TestCommissionsSetup


@tagged("commission_subscription", "post_install", "-at_install")
class TestSaleSubscription(TestCommissionsSetup):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("base.group_user").write(
            {"implied_ids": [(4, cls.env.ref("sale.group_sale_order_template").id)]}
        )

    def test_referrer_commission_plan_changed(self):
        self.referrer.commission_plan_id = self.gold_plan
        form = Form(self.env["sale.order"])
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.template_id = self.template_yearly
        so = form.save()

        self.referrer.commission_plan_id = self.silver_plan
        self.assertEqual(so.commission_plan_id, self.silver_plan)
        self.referrer.commission_plan_id = self.gold_plan
        self.assertEqual(so.commission_plan_id, self.gold_plan)

        form = Form(self.env["sale.order"])
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.template_id = self.template_yearly
        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 1
        sub = form.save()

        self.referrer.commission_plan_id = self.silver_plan
        self.assertEqual(sub.commission_plan_id, self.silver_plan)

        sub.commission_plan_frozen = True
        self.referrer.commission_plan_id = self.gold_plan
        self.assertEqual(sub.commission_plan_id, self.silver_plan)

    def test_referrer_grade_changed(self):
        self.referrer.grade_id = self.gold
        self.referrer._onchange_grade_id()
        form = Form(self.env["sale.order"])
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.template_id = self.template_yearly
        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 1
        sub = form.save()

        self.referrer.grade_id = self.silver
        self.referrer._onchange_grade_id()
        self.assertEqual(sub.commission_plan_id, self.silver_plan)

        sub.commission_plan_frozen = True
        self.referrer.grade_id = self.gold
        self.referrer._onchange_grade_id()
        self.assertEqual(sub.commission_plan_id, self.silver_plan)

    def test_sub_data_forwarded_to_renewal(self):
        self.referrer.commission_plan_id = self.gold_plan

        form = Form(
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_context(tracking_disable=True),
            view=self.env.ref("sale_subscription.sale_subscription_primary_form_view"),
        )
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.plan_id = self.plan_month
        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 1

        form.end_date = fields.Date.today()
        so = form.save()
        so.action_confirm()
        so.next_invoice_date += relativedelta(months=1)
        res = so.prepare_renewal_order()
        res_id = res["res_id"]
        renewal_so = self.env["sale.order"].browse(res_id)
        renewal_so.line_ids.product_qty = 1
        self.assertEqual(renewal_so.referrer_id, so.referrer_id)
        self.assertEqual(renewal_so.commission_plan_id, so.commission_plan_id)

    def test_compute_commission(self):
        self.referrer.commission_plan_id = self.gold_plan

        form = Form(
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_context(tracking_disable=True)
        )
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        self.worker.recurring_invoice = False
        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 2

        so = form.save()
        so.pricelist_id = self.usd_8
        so.action_confirm()

        self.assertEqual(so.commission, 180)

    def test_commission_plan_assignation(self):
        self.referrer.commission_plan_id = self.gold_plan

        form = Form(
            self.env["sale.order"].with_context(tracking_disable=True),
            view=self.env.ref("sale_subscription.sale_subscription_primary_form_view"),
        )
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.template_id = self.template_yearly
        form.pricelist_id = self.usd_8

        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 2

        form.commission_plan_frozen = True
        form.commission_plan_id = self.env["commission.plan"]

        sub = form.save()
        sub.action_confirm()
        sub._cron_recurring_create_invoice()
        res = sub.prepare_renewal_order()
        res_id = res["res_id"]
        renewal_so = self.env["sale.order"].browse(res_id)
        renewal_so.line_ids.product_qty = 2
        renewal_so.action_confirm()

        inv = renewal_so._create_invoices()
        inv.action_post()
        self._pay_invoice(inv)

        self.assertFalse(inv.commission_po_line_id)

        renewal_so.commission_plan_id = self.greedy_plan

        res = renewal_so.prepare_renewal_order()
        res_id = res["res_id"]
        renewal_so_2 = self.env["sale.order"].browse(res_id)
        renewal_so_2.line_ids.product_qty = 1
        renewal_so_2.action_confirm()

        inv = renewal_so_2._create_invoices()
        inv.action_post()
        self._pay_invoice(inv)

        self.assertEqual(
            inv.commission_po_line_id.price_subtotal, 18, "Commission is wrong"
        )

        renewal_so_2.commission_plan_frozen = False
        self.assertEqual(renewal_so_2.commission_plan_id, self.gold_plan)

        res = renewal_so_2.prepare_renewal_order()
        res_id = res["res_id"]
        renewal_so_3 = self.env["sale.order"].browse(res_id)
        renewal_so_3.line_ids.product_qty = 2
        renewal_so_3.action_confirm()

        inv = renewal_so_3._create_invoices()
        inv.action_post()
        self._pay_invoice(inv)

        self.assertEqual(
            inv.commission_po_line_id.price_subtotal, 180, "Commission is wrong"
        )

    def test_commission_plan_frozen(self):
        self.referrer.commission_plan_id = self.gold_plan

        form = Form(self.env["sale.order"])
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.template_id = self.template_yearly
        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 1
        form.commission_plan_frozen = True
        form.commission_plan_id = self.silver_plan
        sub_A = form.save()
        sub_A.action_confirm()
        sub_A._cron_recurring_create_invoice()
        self.assertEqual(sub_A.commission_plan_id, self.silver_plan)
        self.assertEqual(sub_A.commission_plan_frozen, True)

        form = Form(self.env["sale.order"])
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.template_id = self.template_yearly
        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 1
        form.commission_plan_frozen = True
        form.commission_plan_id = self.silver_plan
        form.commission_plan_frozen = False
        sub_B = form.save()
        sub_B.action_confirm()
        sub_B._cron_recurring_create_invoice()
        self.assertEqual(sub_B.commission_plan_id, self.gold_plan)
        self.assertEqual(sub_B.commission_plan_frozen, False)

        form = Form(self.env["sale.order"])
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.template_id = self.template_yearly
        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 1
        form.commission_plan_frozen = True
        sub_C = form.save()
        sub_C.action_confirm()
        sub_C._cron_recurring_create_invoice()
        self.assertEqual(sub_C.commission_plan_id, self.gold_plan)
        self.assertEqual(sub_C.commission_plan_frozen, True)

        sub_A_renew_id = sub_A.prepare_renewal_order()["res_id"]
        sub_A_renew = self.env["sale.order"].browse(sub_A_renew_id)
        self.assertEqual(sub_A_renew.commission_plan_id, self.silver_plan)

        sub_A.commission_plan_frozen = False
        sub_A_renew_id = sub_A.prepare_renewal_order()["res_id"]
        sub_A_renew = self.env["sale.order"].browse(sub_A_renew_id)
        self.assertEqual(sub_A_renew.commission_plan_id, self.gold_plan)

        sub_C_renew_id = sub_C.prepare_renewal_order()["res_id"]
        sub_C_renew = self.env["sale.order"].browse(sub_C_renew_id)
        self.assertEqual(sub_C_renew.commission_plan_frozen, False)
