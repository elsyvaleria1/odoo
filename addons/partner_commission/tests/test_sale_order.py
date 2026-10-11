from odoo.fields import Command
from odoo.tests import Form, tagged

from odoo.addons.partner_commission.tests.setup import TestCommissionsSetup


@tagged("commission_sale", "post_install", "-at_install")
class TestSaleOrder(TestCommissionsSetup):
    def test_referrer_commission_plan_changed(self):
        self.referrer.commission_plan_id = self.gold_plan

        form = Form(
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_context(tracking_disable=True)
        )
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        so = form.save()

        self.assertEqual(so.commission_plan_id, self.gold_plan)

        self.referrer.commission_plan_id = self.silver_plan
        self.assertEqual(so.commission_plan_id, self.silver_plan)

    def test_referrer_grade_changed(self):
        self.referrer.grade_id = self.gold
        self.referrer._onchange_grade_id()
        form = Form(
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_context(tracking_disable=True)
        )
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        so = form.save()

        self.referrer.grade_id = self.silver
        self.referrer._onchange_grade_id()
        self.assertEqual(so.commission_plan_id, self.silver_plan)

    def test_so_data_forwarded_to_sub(self):
        self.referrer.commission_plan_id = self.gold_plan

        form = Form(
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_context(tracking_disable=True),
            view=self.env.ref("sale_subscription.sale_subscription_primary_form_view"),
        )
        form.partner_id = self.customer
        form.referrer_id = self.referrer
        form.plan_id = self.plan_year

        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 1

        so = form.save()
        so.action_confirm()

        so.commission_plan_id = self.silver_plan
        self.assertEqual(so.commission_plan_id, self.silver_plan)
        self.assertEqual(so.commission_plan_frozen, True)

    def test_so_data_forwarded_to_invoice(self):
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
            line.product_qty = 1

        so = form.save()
        so.action_confirm()

        inv = self.env["account.move"].create(so._prepare_invoice_vals())

        self.assertEqual(inv.referrer_id, so.referrer_id)

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
        so.pricelist_id = self.eur_20
        so.action_confirm()

        self.assertEqual(so.commission, 150)

    def test_so_referrer_id_to_invoice(self):
        self.referrer.commission_plan_id = self.gold_plan
        self.worker.recurring_invoice = False
        form = Form(
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_context(tracking_disable=True)
        )
        form.partner_id = self.customer
        form.referrer_id = self.referrer

        with form.line_ids.new() as line:
            line.name = self.worker.name
            line.product_id = self.worker
            line.product_qty = 1

        so = form.save()
        so.action_confirm()

        invoice_wizard = (
            self.env["wizard.sale.order.invoice"]
            .with_context(tracking_disable=True)
            .create(
                {
                    "advance_payment_method": "fixed",
                    "sale_order_ids": [Command.set(so.ids)],
                    "fixed_amount": 100,
                }
            )
        )

        inv = invoice_wizard._create_invoices(so)
        self.assertEqual(inv.referrer_id, so.referrer_id)

    def test_commission_plan_apply_sequence(self):
        category_main = self.env["product.category"].create({"name": "All"})
        category_sub = self.env["product.category"].create(
            {
                "name": "Category",
                "parent_id": category_main.id,
            },
        )
        product_other, product_test = self.env["product.product"].create(
            [
                {
                    "name": "product_other",
                    "categ_id": category_sub.id,
                    "list_price": 100.0,
                },
                {
                    "name": "product_test",
                    "categ_id": category_main.id,
                    "list_price": 100.0,
                },
            ]
        )
        plan = self.env["commission.plan"].create(
            {
                "name": "New Plan",
                "product_id": self.env.ref("partner_commission.product_commission").id,
                "commission_rule_ids": [
                    (
                        0,
                        0,
                        {
                            "category_id": category_main.id,
                            "product_id": None,
                            "rate": 10,
                            "sequence": 1,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "category_id": category_main.id,
                            "product_id": product_test.id,
                            "rate": 20,
                            "sequence": 0,
                        },
                    ),
                ],
            }
        )
        self.referrer.commission_plan_id = plan
        form = Form(
            self.env["sale.order"]
            .with_user(self.salesman)
            .with_context(tracking_disable=True)
        )
        form.partner_id = self.customer
        form.referrer_id = self.referrer

        with form.line_ids.new() as line:
            line.name = product_test.name
            line.product_id = product_test
            line.product_qty = 1
        so = form.save()

        self.assertEqual(so.commission, 20)

        old_commission = so.commission
        with form.line_ids.new() as line:
            line.name = product_other.name
            line.product_id = product_other
            line.product_qty = 1
        so = form.save()

        self.assertEqual(
            so.commission, 10 + old_commission
        )

    def test_subcontracted_service_po_with_referrer(self):
        self.env["product.supplierinfo"].create(
            {
                "partner_id": self.customer.id,
                "product_tmpl_id": self.worker.product_tmpl_id.id,
            }
        )
        self.worker.write(
            {"type": "service", "service_to_purchase": True, "recurring_invoice": False}
        )
        sale_orders = self.env["sale.order"].create(
            [
                {
                    "partner_id": self.customer.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.worker.id,
                                "product_qty": 1,
                            }
                        )
                    ],
                },
                {
                    "partner_id": self.customer.id,
                    "referrer_id": self.referrer.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.worker.id,
                                "product_qty": 2,
                            }
                        )
                    ],
                },
            ]
        )
        sale_orders.action_confirm()

        purchase_orders = self.env["purchase.order"].search(
            [("partner_id", "=", self.customer.id), ("state", "=", "draft")]
        )

        self.assertEqual(len(purchase_orders), 1, "Only one PO should be created.")
        self.assertEqual(
            len(purchase_orders.line_ids),
            2,
            "Two Sale Order line should be linked to a PO line.",
        )

    def test_invoice_with_referrer(self):
        product = self.worker
        self.referrer.commission_plan_id = self.env["commission.plan"].create(
            {
                "name": "Test Plan",
                "product_id": product.id,
                "commission_rule_ids": [
                    (
                        0,
                        0,
                        {
                            "category_id": product.categ_id.id,
                            "rate": 10,
                        },
                    ),
                ],
            }
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
                "referrer_id": self.referrer.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "price_unit": 100,
                        },
                    ),
                ],
            }
        )
        invoice.action_post()
        action_register_payment = invoice.action_force_register_payment()
        wizard = (
            self.env[action_register_payment["res_model"]]
            .with_context(action_register_payment["context"])
            .create({})
        )
        action_create_payment = wizard.action_create_payments()
        payment = self.env[action_create_payment["res_model"]].browse(
            action_create_payment["res_id"]
        )

        self.assertTrue(payment)
        self.assertEqual(payment.invoice_ids, invoice)
