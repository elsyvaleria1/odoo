from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install")
class TestSaleAgreement(SaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product.list_price = 50.0
        cls.agreement = cls.env["sale.agreement"].create(
            {
                "partner_id": cls.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": cls.product.id,
                            "product_qty": 100.0,
                            "price_unit": 42.0,
                        }
                    )
                ],
            }
        )

    def test_a_blanket_order_is_named_from_its_sequence(self):
        self.assertTrue(self.agreement.name.startswith("SBO"))

    def test_confirming_needs_a_price_and_a_quantity_on_every_line(self):
        self.agreement.line_ids.price_unit = 0.0
        with self.assertRaisesRegex(UserError, "missing a price"):
            self.agreement.action_confirm()
        self.agreement.line_ids.price_unit = 42.0
        self.agreement.line_ids.product_qty = 0.0
        with self.assertRaisesRegex(UserError, "missing a quantity"):
            self.agreement.action_confirm()

    def _order_against_agreement(self, qty):
        self.agreement.action_confirm()
        with Form(self.env["sale.order"]) as order_form:
            order_form.partner_id = self.partner
            order_form.agreement_id = self.agreement
            with order_form.line_ids.edit(0) as line:
                line.product_qty = qty
        return order_form.record

    def test_an_order_against_the_agreement_takes_its_products_and_prices(self):
        order = self._order_against_agreement(10.0)
        self.assertEqual(order.line_ids.product_id, self.product)
        self.assertEqual(order.line_ids.price_unit, 42.0)
        self.assertIn(self.agreement.name, order.origin)

    def test_confirmed_orders_count_against_the_agreed_quantity(self):
        order = self._order_against_agreement(10.0)
        self.assertEqual(self.agreement.line_ids.qty_ordered, 0.0)
        order.action_confirm()
        self.assertEqual(self.agreement.line_ids.qty_ordered, 10.0)
        self.assertEqual(self.agreement.order_count, 1)

    def test_an_agreement_is_not_closed_while_a_quotation_is_open(self):
        self._order_against_agreement(10.0)
        with self.assertRaisesRegex(UserError, "cancel its related quotations"):
            self.agreement.action_done()

    def test_the_agreed_price_follows_the_unit_of_measure(self):
        dozen = self.env.ref("uom.product_uom_dozen")
        order = self._order_against_agreement(1.0)
        order.line_ids.product_uom_id = dozen
        self.assertAlmostEqual(order.line_ids.price_unit, 42.0 * 12)


@tagged("post_install", "-at_install")
class TestSaleAgreementCommitment(SaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product.list_price = 50.0
        cls.agreement = cls.env["sale.agreement"].create(
            {
                "partner_id": cls.partner.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": cls.product.id,
                            "product_qty": 100.0,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )

    def _order(self, qty, agreement=None):
        agreement = agreement or self.agreement
        if agreement.state == "draft":
            agreement.action_confirm()
        with Form(self.env["sale.order"]) as order_form:
            order_form.partner_id = self.partner
            order_form.agreement_id = agreement
            order_form.date_order = "2026-06-01 10:00:00"
            with order_form.line_ids.edit(0) as line:
                line.product_qty = qty
        return order_form.record

    def test_an_order_line_links_to_its_agreement_line(self):
        order = self._order(30.0)

        self.assertEqual(order.line_ids.agreement_line_id, self.agreement.line_ids)

    def test_consumption_is_stored_and_released_by_a_cancellation(self):
        order = self._order(30.0)
        order.action_confirm()

        self.assertRecordValues(
            self.agreement.line_ids,
            [{"qty_ordered": 30.0, "qty_remaining": 70.0, "amount_ordered": 300.0}],
        )
        self.assertAlmostEqual(self.agreement.consumed_percent, 30.0)

        order.action_cancel()

        self.assertEqual(self.agreement.line_ids.qty_ordered, 0.0)
        self.assertEqual(self.agreement.consumed_percent, 0.0)

    def test_a_credit_note_gives_its_quantity_back_to_the_agreement(self):
        order = self._order(30.0)
        order.action_confirm()
        invoice = order._create_invoices()
        invoice.action_post()

        refund = invoice._reverse_moves()
        refund.invoice_line_ids.quantity = 10.0
        refund.action_post()

        self.assertRecordValues(
            self.agreement.line_ids,
            [{"qty_ordered": 20.0, "qty_remaining": 80.0, "amount_ordered": 200.0}],
        )

    def test_a_quantity_break_lowers_the_agreed_price(self):
        self.agreement.break_ids = [
            Command.create(
                {
                    "line_id": self.agreement.line_ids.id,
                    "min_qty": 50.0,
                    "price_unit": 8.0,
                }
            )
        ]

        self.assertEqual(self._order(30.0).line_ids.price_unit, 10.0)
        self.assertEqual(self._order(60.0).line_ids.price_unit, 8.0)

    def test_a_break_is_unique_per_quantity(self):
        line = self.agreement.line_ids
        self.env["sale.agreement.line.break"].create(
            {
                "agreement_id": self.agreement.id,
                "line_id": line.id,
                "min_qty": 50.0,
                "price_unit": 8.0,
            }
        )

        with self.assertRaises(ValidationError):
            self.env["sale.agreement.line.break"].create(
                {
                    "agreement_id": self.agreement.id,
                    "line_id": line.id,
                    "min_qty": 50.0,
                    "price_unit": 7.0,
                }
            )

    def test_renewing_carries_the_quantity_breaks(self):
        self.agreement.break_ids = [
            Command.create(
                {
                    "line_id": self.agreement.line_ids.id,
                    "min_qty": 50.0,
                    "price_unit": 8.0,
                }
            )
        ]
        self.agreement.action_confirm()

        action = self.agreement.action_renew()
        renewal = self.env["sale.agreement"].browse(action["res_id"])

        self.assertRecordValues(
            renewal.break_ids,
            [{"line_id": renewal.line_ids.id, "min_qty": 50.0, "price_unit": 8.0}],
        )

    def _category_agreement(self):
        seeds = self.env["product.category"].create({"name": "Seeds"})
        corn = self.env["product.category"].create(
            {"name": "Corn", "parent_id": seeds.id}
        )
        hybrid = self.env["product.product"].create(
            {"name": "Hybrid corn", "categ_id": corn.id, "list_price": 50.0}
        )
        self.agreement.line_ids = [
            Command.create({"product_category_id": seeds.id, "discount": 15.0}),
            Command.create({"product_category_id": corn.id, "discount": 20.0}),
        ]
        return hybrid

    def _order_product(self, product, qty):
        self._enable_discounts()
        self.agreement.action_confirm()
        with Form(self.env["sale.order"]) as order_form:
            order_form.partner_id = self.partner
            order_form.agreement_id = self.agreement
            order_form.date_order = "2026-06-01 10:00:00"
            with order_form.line_ids.new() as line:
                line.product_id = product
                line.product_qty = qty
        return order_form.record.line_ids.filtered(
            lambda line: line.product_id == product and line.product_qty == qty
        )

    def test_the_deepest_category_line_discounts_a_product(self):
        hybrid = self._category_agreement()

        line = self._order_product(hybrid, 4.0)

        self.assertEqual(line.agreement_line_id.discount, 20.0)
        self.assertRecordValues(line, [{"price_unit": 50.0, "discount": 20.0}])

    def test_a_product_line_outranks_a_category_line(self):
        self._category_agreement()
        self.product.categ_id = self.env["product.category"].search(
            [("name", "=", "Corn")], limit=1
        )

        line = self._order_product(self.product, 4.0)

        self.assertEqual(line.agreement_line_id.product_id, self.product)
        self.assertRecordValues(line, [{"price_unit": 10.0, "discount": 0.0}])

    def test_a_category_line_needs_its_discount(self):
        seeds = self.env["product.category"].create({"name": "Bulbs"})
        self.agreement.line_ids = [Command.create({"product_category_id": seeds.id})]

        with self.assertRaisesRegex(UserError, "needs the discount it grants"):
            self.agreement.action_confirm()

    def test_a_line_names_a_product_or_a_category(self):
        with self.assertRaises(ValidationError):
            self.agreement.line_ids.product_category_id = self.product.categ_id

    def test_a_contact_of_the_party_orders_under_the_agreement(self):
        contact = self.env["res.partner"].create(
            {"name": "Branch buyer", "parent_id": self.partner.id}
        )
        self.agreement.overrelease_policy = "block"
        self.agreement.action_confirm()
        with Form(self.env["sale.order"]) as order_form:
            order_form.partner_id = contact
            order_form.agreement_id = self.agreement
            order_form.date_order = "2026-06-01 10:00:00"
            with order_form.line_ids.edit(0) as line:
                line.product_qty = 5.0
        order = order_form.record

        offered = self.env["sale.agreement"].search(
            [
                ("state", "=", "confirmed"),
                "|",
                ("partner_id", "=", False),
                (
                    "partner_id.commercial_partner_id",
                    "=",
                    order.commercial_partner_id.id,
                ),
            ]
        )
        self.assertIn(self.agreement, offered)
        self.assertFalse(order._get_agreement_breaches())
        order.action_confirm()
        self.assertEqual(order.line_ids.price_unit, 10.0)

    def test_an_outsider_is_not_a_party_to_the_agreement(self):
        order = self._order(5.0)
        order.partner_id = self.env["res.partner"].create({"name": "Outsider"})

        self.assertIn("is not a party", "\n".join(order._get_agreement_breaches()))

    def test_a_category_line_breaches_no_quantity_commitment(self):
        hybrid = self._category_agreement()
        self.agreement.overrelease_policy = "block"

        line = self._order_product(hybrid, 4.0)
        line.order_id.action_confirm()

        self.assertEqual(line.order_id.state, "done")

    def test_each_line_counts_only_what_was_ordered_against_it(self):
        self.agreement.line_ids = [
            Command.create(
                {"product_id": self.product.id, "product_qty": 5.0, "price_unit": 9.0}
            )
        ]
        first, second = self.agreement.line_ids
        order = self._order(4.0)
        order.line_ids.agreement_line_id = second
        order.action_confirm()

        self.assertEqual(first.qty_ordered, 0.0)
        self.assertEqual(second.qty_ordered, 4.0)
        self.assertAlmostEqual(self.agreement.consumed_percent, 80.0)

    def test_a_value_commitment_counts_amounts(self):
        self.agreement.write({"commitment": "value", "amount_committed": 1000.0})
        order = self._order(40.0)
        order.action_confirm()

        self.assertEqual(self.agreement.amount_ordered, 400.0)
        self.assertEqual(self.agreement.amount_remaining, 600.0)
        self.assertAlmostEqual(self.agreement.consumed_percent, 40.0)

    def test_a_value_commitment_needs_its_amount(self):
        self.agreement.commitment = "value"

        with self.assertRaisesRegex(UserError, "without the amount"):
            self.agreement.action_confirm()

    def test_a_price_agreement_needs_no_quantity(self):
        self.agreement.write({"commitment": "price"})
        self.agreement.line_ids.product_qty = 0.0

        self.agreement.action_confirm()

        self.assertEqual(self.agreement.state, "confirmed")

    def test_the_block_policy_refuses_an_order_beyond_the_commitment(self):
        self.agreement.overrelease_policy = "block"
        order = self._order(120.0)

        self.assertIn("left on", order.agreement_warning)
        with self.assertRaisesRegex(UserError, "goes beyond its agreement"):
            order.action_confirm()

    def test_the_warn_policy_warns_and_confirms(self):
        order = self._order(120.0)

        self.assertIn("120.0 ordered, 100.0 left", order.agreement_warning)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_the_allow_policy_says_nothing(self):
        self.agreement.overrelease_policy = "allow"
        order = self._order(120.0)

        self.assertFalse(order.agreement_warning)

    def test_an_order_outside_the_validity_is_a_breach(self):
        self.agreement.overrelease_policy = "block"
        order = self._order(1.0)
        order.date_order = "2027-02-01 10:00:00"

        with self.assertRaisesRegex(UserError, "outside"):
            order.action_confirm()

    def test_renewing_copies_the_agreement_into_the_next_period(self):
        self.agreement.action_confirm()

        action = self.agreement.action_renew()

        renewal = self.env["sale.agreement"].browse(action["res_id"])
        self.assertRecordValues(
            renewal,
            [
                {
                    "state": "draft",
                    "previous_agreement_id": self.agreement.id,
                    "date_start": fields.Date.to_date("2027-01-01"),
                    "date_end": fields.Date.to_date("2027-12-31"),
                }
            ],
        )
        self.assertEqual(renewal.line_ids.price_unit, 10.0)
        self.assertNotEqual(renewal.name, self.agreement.name)

    def test_reminders_are_scheduled_once(self):
        today = fields.Date.context_today(self.agreement)
        self.agreement.date_end = today + timedelta(days=10)
        self.agreement.date_start = today - timedelta(days=10)
        self._order(95.0).action_confirm()

        self.env["sale.agreement"]._cron_remind()
        self.env["sale.agreement"]._cron_remind()

        self.assertEqual(len(self.agreement.activity_ids), 2)
        self.assertTrue(self.agreement.reminded_expiry)
        self.assertTrue(self.agreement.reminded_consumption)
