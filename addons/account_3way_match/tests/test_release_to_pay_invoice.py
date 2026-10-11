from odoo import Command, fields
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestReleaseToPayInvoice(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user.group_ids |= cls.quick_ref("purchase.group_purchase_user")
        cls.partner = cls.env["res.partner"].create({"name": "Zizizapartner"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "VR Computer",
                "standard_price": 2500.0,
                "list_price": 2899.0,
                "type": "service",
                "default_code": "VR-01",
                "weight": 1.0,
                "bill_policy": "transferred",
            }
        )
        cls.other_currency = cls.setup_other_currency("HRK", rounding=0.001)

    def check_release_to_pay_scenario(
        self, ordered_qty, scenario, invoicing_policy="transferred", order_price=500.0
    ):
        self.product.bill_policy = invoicing_policy

        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": self.product.name,
                            "product_id": self.product.id,
                            "product_qty": ordered_qty,
                            "product_uom_id": self.product.uom_id.id,
                            "price_unit": order_price,
                            "date_commitment": fields.Datetime.now(),
                        },
                    )
                ],
            }
        )
        purchase_order.action_confirm()

        invoices_list = []
        purchase_line = purchase_order.line_ids[-1]
        AccountMove = self.env["account.move"].with_context(
            default_move_type="in_invoice"
        )
        for action, params in scenario:
            if action == "invoice":
                move_form = Form(
                    AccountMove.with_context(default_purchase_id=purchase_order.id)
                )
                with move_form.invoice_line_ids.edit(0) as line_form:
                    if "price" in params:
                        line_form.price_unit = params["price"]
                    if "qty" in params:
                        line_form.quantity = params["qty"]
                new_invoice = move_form.save()
                new_invoice.write(
                    {
                        "invoice_line_ids": [
                            Command.create(
                                {"display_type": "line_section", "name": "Section"}
                            ),
                            Command.create(
                                {"display_type": "line_note", "name": "Note"}
                            ),
                        ]
                    }
                )
                invoices_list.append(new_invoice)

                self.assertEqual(
                    new_invoice.release_to_pay,
                    params["rslt"],
                    "Wrong invoice release to pay status for scenario " + str(scenario),
                )

            elif action == "receive":
                purchase_line.write(
                    {"qty_transferred": params["qty"]}
                )

                if "rslt" in params:
                    for invoice_index, status in params["rslt"]:
                        self.assertEqual(
                            invoices_list[invoice_index].release_to_pay,
                            status,
                            "Wrong invoice release to pay status for scenario "
                            + str(scenario),
                        )

    def test_3_way_match(self):
        self.check_release_to_pay_scenario(
            10,
            [("receive", {"qty": 5}), ("invoice", {"qty": 5, "rslt": "yes"})],
            invoicing_policy="ordered",
        )
        self.check_release_to_pay_scenario(
            10,
            [("receive", {"qty": 5}), ("invoice", {"qty": 10, "rslt": "yes"})],
            invoicing_policy="ordered",
        )
        self.check_release_to_pay_scenario(
            10, [("invoice", {"qty": 10, "rslt": "yes"})], invoicing_policy="ordered"
        )
        self.check_release_to_pay_scenario(
            10,
            [
                ("invoice", {"qty": 5, "rslt": "yes"}),
                ("receive", {"qty": 5}),
                ("invoice", {"qty": 6, "rslt": "exception"}),
            ],
            invoicing_policy="ordered",
        )
        self.check_release_to_pay_scenario(
            10,
            [
                ("invoice", {"qty": 10, "rslt": "yes"}),
                ("invoice", {"qty": 10, "rslt": "no"}),
            ],
            invoicing_policy="ordered",
        )
        self.check_release_to_pay_scenario(
            10, [("receive", {"qty": 5}), ("invoice", {"qty": 5, "rslt": "yes"})]
        )
        self.check_release_to_pay_scenario(
            10, [("receive", {"qty": 5}), ("invoice", {"qty": 10, "rslt": "exception"})]
        )
        self.check_release_to_pay_scenario(10, [("invoice", {"qty": 5, "rslt": "no"})])
        self.check_release_to_pay_scenario(
            10,
            [
                ("invoice", {"qty": 5, "rslt": "no"}),
                ("receive", {"qty": 5, "rslt": [(-1, "yes")]}),
            ],
        )
        self.check_release_to_pay_scenario(
            10,
            [
                ("invoice", {"qty": 5, "rslt": "no"}),
                ("receive", {"qty": 3, "rslt": [(-1, "exception")]}),
            ],
        )
        self.check_release_to_pay_scenario(
            10,
            [
                ("invoice", {"qty": 5, "rslt": "no"}),
                ("receive", {"qty": 10, "rslt": [(-1, "yes")]}),
            ],
        )

        self.check_release_to_pay_scenario(
            10,
            [
                ("receive", {"qty": 5}),
                ("invoice", {"qty": 5, "rslt": "exception", "price": 42}),
            ],
        )
        self.check_release_to_pay_scenario(
            10,
            [
                ("receive", {"qty": 5}),
                ("invoice", {"qty": 5, "rslt": "exception", "price": 42}),
            ],
            invoicing_policy="ordered",
        )

    def _confirmed_order(self, ordered_qty=10, price=500.0, policy="ordered"):
        self.product.bill_policy = policy
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": self.product.name,
                            "product_id": self.product.id,
                            "product_qty": ordered_qty,
                            "product_uom_id": self.product.uom_id.id,
                            "price_unit": price,
                            "date_commitment": fields.Datetime.now(),
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        return order

    def _bill_for(self, order_lines, quantity, price=500.0, uom=None):
        line_vals = {
            "product_id": order_lines[0].product_id.id,
            "quantity": quantity,
            "price_unit": price,
            "purchase_line_ids": [Command.set(order_lines.ids)],
        }
        if uom:
            line_vals["product_uom_id"] = uom.id
        return self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner.id,
                "invoice_date": "2026-01-01",
                "invoice_line_ids": [Command.create(line_vals)],
            }
        )

    def _confirmed_order_lines(self, quantities, price=500.0, policy="ordered"):
        self.product.bill_policy = policy
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": self.product.name,
                            "product_id": self.product.id,
                            "product_qty": qty,
                            "product_uom_id": self.product.uom_id.id,
                            "price_unit": price,
                            "date_commitment": fields.Datetime.now(),
                        }
                    )
                    for qty in quantities
                ],
            }
        )
        order.action_confirm()
        return order

    def test_bill_line_spanning_two_order_lines_is_counted_once(self):
        order = self._confirmed_order_lines([6, 4])
        bill = self._bill_for(order.line_ids, 10)

        self.assertEqual(bill.invoice_line_ids.can_be_paid, "yes")
        self.assertEqual(bill.release_to_pay, "yes")

    def test_over_billing_is_seen_across_units_of_measure(self):
        dozen = self.env.ref("base.product_uom_dozen")
        order = self._confirmed_order_lines([13], price=1.0)

        first = self._bill_for(order.line_ids, 1, price=12.0, uom=dozen)
        self.assertEqual(first.invoice_line_ids.can_be_paid, "yes")

        second = self._bill_for(order.line_ids, 1, price=12.0, uom=dozen)
        self.assertEqual(second.invoice_line_ids.can_be_paid, "exception")

    def test_same_money_in_another_unit_is_not_a_price_change(self):
        dozen = self.env.ref("base.product_uom_dozen")
        order = self._confirmed_order_lines([12], price=1.0)

        bill = self._bill_for(order.line_ids, 1, price=12.0, uom=dozen)

        self.assertEqual(bill.invoice_line_ids.can_be_paid, "yes")

    def test_a_discount_is_a_price_change(self):
        order = self._confirmed_order_lines([10], price=500.0)

        bill = self._bill_for(order.line_ids, 10)
        bill.invoice_line_ids.discount = 50.0

        self.assertEqual(bill.invoice_line_ids.can_be_paid, "exception")
        self.assertEqual(bill.release_to_pay, "exception")

    def test_a_price_raised_on_the_order_reopens_the_bill(self):
        order = self._confirmed_order_lines([10], price=500.0)
        bill = self._bill_for(order.line_ids, 10)
        self.assertEqual(bill.release_to_pay, "yes")

        order.line_ids.price_unit = 999.0
        self.env.flush_all()
        bill.invalidate_recordset()
        bill.invoice_line_ids.invalidate_recordset()

        self.assertEqual(bill.invoice_line_ids.can_be_paid, "exception")
        self.assertEqual(bill.release_to_pay, "exception")

    def test_a_discount_given_on_the_order_reopens_the_bill(self):
        order = self._confirmed_order_lines([10], price=500.0)
        bill = self._bill_for(order.line_ids, 10)
        self.assertEqual(bill.release_to_pay, "yes")

        order.line_ids.discount = 50.0
        self.env.flush_all()
        bill.invalidate_recordset()
        bill.invoice_line_ids.invalidate_recordset()

        self.assertEqual(bill.invoice_line_ids.can_be_paid, "exception")

    def test_a_changed_billing_policy_reopens_the_bill(self):
        order = self._confirmed_order_lines([10], policy="transferred")
        bill = self._bill_for(order.line_ids, 5)
        self.assertEqual(bill.invoice_line_ids.can_be_paid, "no")

        self.product.bill_policy = "ordered"
        self.env.flush_all()
        bill.invalidate_recordset()
        bill.invoice_line_ids.invalidate_recordset()

        self.assertEqual(bill.invoice_line_ids.can_be_paid, "yes")

    def test_a_purchase_receipt_counts_against_what_was_ordered(self):
        order = self._confirmed_order_lines([10], price=500.0)
        receipt = self._bill_for(order.line_ids, 100)
        receipt.move_type = "in_receipt"
        self.env.flush_all()
        receipt.invoice_line_ids.invalidate_recordset()

        self.assertEqual(receipt.invoice_line_ids.can_be_paid, "exception")
        self.assertEqual(receipt.release_to_pay, "exception")

    def test_mixed_product_order_lines_are_an_exception(self):
        other = self.env["product.product"].create(
            {
                "name": "Other product",
                "type": "service",
                "standard_price": 500.0,
                "list_price": 500.0,
                "bill_policy": "transferred",
            }
        )
        self.product.bill_policy = "ordered"
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": product.name,
                            "product_id": product.id,
                            "product_qty": 10,
                            "product_uom_id": product.uom_id.id,
                            "price_unit": 500.0,
                            "date_commitment": fields.Datetime.now(),
                        }
                    )
                    for product in (self.product, other)
                ],
            }
        )
        order.action_confirm()

        bill = self._bill_for(order.line_ids, 10)

        self.assertEqual(bill.invoice_line_ids.can_be_paid, "exception")
        self.assertEqual(bill.release_to_pay, "exception")

    def test_duplicate_does_not_carry_the_forced_status(self):
        order = self._confirmed_order()
        bill = self._bill_for(order.line_ids, 10)
        bill.write({"force_release_to_pay": True, "release_to_pay_manual": "yes"})
        self.assertEqual(bill.release_to_pay, "yes")

        duplicate = bill.copy()

        self.assertFalse(duplicate.invoice_line_ids.purchase_line_ids)
        self.assertFalse(duplicate.force_release_to_pay)
        self.assertEqual(duplicate.release_to_pay, "exception")

    def test_forced_status_follows_a_changed_manual_verdict(self):
        order = self._confirmed_order()
        bill = self._bill_for(order.line_ids, 10)
        bill.write({"force_release_to_pay": True, "release_to_pay_manual": "yes"})
        self.assertEqual(bill.release_to_pay, "yes")

        bill.release_to_pay_manual = "no"
        bill.invalidate_recordset()

        self.assertEqual(bill.release_to_pay, "no")

    def test_forced_bill_without_a_manual_verdict_is_an_exception(self):
        order = self._confirmed_order()
        bill = self._bill_for(order.line_ids, 10)
        bill.write({"force_release_to_pay": True, "release_to_pay_manual": "yes"})

        bill.release_to_pay_manual = False
        bill.invalidate_recordset()

        self.assertEqual(bill.release_to_pay, "exception")

    def test_a_customer_invoice_carries_no_release_to_pay_verdict(self):
        invoice = self.init_invoice(
            "out_invoice", partner=self.partner, amounts=[100.0], post=False
        )

        self.assertFalse(invoice.release_to_pay)
        self.assertFalse(any(invoice.invoice_line_ids.mapped("can_be_paid")))

    def test_amount_currency_edit(self):
        move_form = Form(
            self.env["account.move"].with_context(default_move_type="out_invoice")
        )
        move_form.invoice_date = fields.Date.from_string("2023-01-01")
        move_form.partner_id = self.partner_a
        move_form.currency_id = self.other_currency
        with move_form.invoice_line_ids.new() as line_form:
            line_form.quantity = 1
            line_form.price_unit = 10
        move_form.save()
        with move_form.line_ids.edit(0) as line_form:
            line_form.amount_currency = -30
        move_form.save()
        self.assertEqual(move_form.line_ids.edit(0).amount_currency, -30)

    def test_an_unconvertible_unit_is_an_exception_not_a_traceback(self):
        order = self._confirmed_order_lines([10], price=100.0)
        bill = self._bill_for(order.line_ids, 10, price=100.0)
        line = bill.invoice_line_ids.filtered(lambda l: l.purchase_line_ids)
        self.assertEqual(line.can_be_paid, "yes")

        hours = self.env.ref("base.product_uom_hour")
        self.assertFalse(line.product_uom_id._has_common_reference(hours))
        self.env.cr.execute(
            "UPDATE account_move_line SET product_uom_id = %s WHERE id = %s",
            (hours.id, line.id),
        )
        line.invalidate_recordset()

        self.env.add_to_compute(line._fields["can_be_paid"], line)
        self.env["account.move.line"].flush_model()

        self.assertEqual(line.can_be_paid, "exception")

    def test_a_bill_line_is_judged_against_its_own_product(self):
        order = self._confirmed_order_lines([10], price=500.0)
        order.line_ids.qty_transferred = 10.0
        bill = self._bill_for(order.line_ids, 5, price=500.0)
        line = bill.invoice_line_ids.filtered(lambda l: l.purchase_line_ids)
        self.assertEqual(line.can_be_paid, "yes")

        other = self.env["product.product"].create(
            {
                "name": "Not what was ordered",
                "type": "service",
                "standard_price": 500.0,
                "list_price": 500.0,
                "uom_id": self.product.uom_id.id,
                "bill_policy": self.product.bill_policy,
            }
        )
        line.write({"product_id": other.id, "price_unit": 500.0, "quantity": 5})
        line.flush_recordset()

        self.assertEqual(line.purchase_line_ids.product_id, self.product)
        self.assertEqual(line.can_be_paid, "exception")

    def test_a_rounding_artefact_is_not_a_received_quantity(self):
        order = self._confirmed_order_lines([10, 10, 10], policy="transferred")
        order.line_ids[0].qty_transferred = 0.1
        order.line_ids[1].qty_transferred = 0.2
        order.line_ids[2].qty_transferred = -0.3

        uom = order.line_ids[0].product_uom_id
        received = sum(
            l.product_uom_id._get_quantity_in_unit(l.qty_transferred, uom)
            for l in order.line_ids
        )
        self.assertNotEqual(received, 0.0, "the artefact this test exists for")

        bill = self._bill_for(order.line_ids, 5)
        line = bill.invoice_line_ids.filtered(lambda l: l.purchase_line_ids)
        self.assertEqual(line.can_be_paid, "no")

    def test_a_sub_cent_price_change_is_still_a_price_change(self):
        self.env["decimal.precision"].search(
            [("name", "=", "Product Price")]
        ).digits = 4
        self.env.registry.clear_cache()

        order = self._confirmed_order_lines([10], price=100.1234)
        self.assertEqual(order.currency_id.decimal_places, 2)

        bill = self._bill_for(order.line_ids, 10, price=100.1249)
        line = bill.invoice_line_ids.filtered(lambda l: l.purchase_line_ids)

        self.assertEqual(
            order.currency_id.compare_amounts(
                order.line_ids.price_unit, line.price_unit
            ),
            0,
        )
        self.assertEqual(line.can_be_paid, "exception")

    def test_the_same_price_in_another_currency_is_not_a_price_change(self):
        order = self._confirmed_order_lines([10], price=500.0)
        bill = self._bill_for(order.line_ids, 10, price=500.0)
        line = bill.invoice_line_ids.filtered(lambda l: l.purchase_line_ids)
        self.assertEqual(line.currency_id, order.currency_id)
        self.assertEqual(line.can_be_paid, "yes")

        bill.currency_id = self.other_currency
        rate = self.env["res.currency"]._get_conversion_rate(
            order.currency_id,
            self.other_currency,
            bill.company_id,
            bill.invoice_date,
        )
        line.price_unit = 500.0 * rate
        line.flush_recordset()
        self.assertNotEqual(line.currency_id, order.currency_id)
        self.assertEqual(line.can_be_paid, "yes")
