from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestApprovalModeCriteria(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("target_model", "=", False)],
        ).write({"active": False})

        cls.vendor = cls.env["res.partner"].create(
            {"name": "Mode Vendor", "supplier_rank": 1},
        )
        cls.other_vendor = cls.env["res.partner"].create(
            {"name": "Other Vendor", "supplier_rank": 1},
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Mode Product", "type": "consu"},
        )

    def _make_category(self, **values):
        return self.env["approval.category"].create(
            {
                "name": "Mode Category",
                "approval_type": "purchase",
                "target_model": False,
                "approval_minimum": 1,
                **values,
            },
        )

    def _make_order(self, price=5000.0, partner=None):
        return self.env["purchase.order"].create(
            {
                "partner_id": (partner or self.vendor).id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": price,
                        },
                    ),
                ],
            },
        )

    def test_user_trigger_option_is_gone(self):
        modes = dict(
            self.env["approval.category"]._fields["order_approval_mode"].selection,
        )
        self.assertNotIn("user", modes)

    def test_switching_trigger_clears_the_criteria_it_hides(self):
        category = self._make_category(
            order_approval_mode="partner",
            order_partner_ids=[Command.set(self.other_vendor.ids)],
        )
        form_category = category.new(origin=category)
        form_category.order_approval_mode = "amount"
        form_category._onchange_order_approval_mode()
        self.assertFalse(form_category.order_partner_ids)

    def test_new_purchase_category_defaults_to_combined(self):
        category = self.env["approval.category"].create(
            {"name": "Defaulted Category", "approval_type": "purchase"},
        )

        self.assertEqual(category.order_approval_mode, "combined")

    def test_clearing_the_trigger_keeps_the_configured_criteria(self):
        category = self._make_category(
            order_approval_mode="combined",
            order_amount_min=1000.0,
            order_amount_max=5000.0,
            order_partner_ids=[Command.set(self.other_vendor.ids)],
            check_debit_limit=True,
            debit_limit_threshold=20000.0,
        )

        form_category = category.new(origin=category)
        form_category.order_approval_mode = False

        self.assertEqual(form_category._get_approval_mode_hidden_criteria(), ())

        form_category._onchange_order_approval_mode()

        self.assertEqual(form_category.order_amount_min, 1000.0)
        self.assertEqual(form_category.order_amount_max, 5000.0)
        self.assertEqual(form_category.order_partner_ids._origin, self.other_vendor)
        self.assertTrue(form_category.check_debit_limit)
        self.assertEqual(form_category.debit_limit_threshold, 20000.0)

    def test_a_wiped_category_would_match_every_order(self):
        category = self._make_category(order_approval_mode="combined")

        self.assertTrue(
            category._is_applicable_for(self._make_order(partner=self.other_vendor)),
        )

    def test_stale_hidden_criterion_still_constrains_matching(self):
        category = self._make_category(
            order_approval_mode="amount",
            order_amount_min=1000.0,
            order_partner_ids=[Command.set(self.other_vendor.ids)],
        )
        order = self._make_order(price=5000.0)
        self.assertTrue(category._is_matching_amount(order))
        self.assertFalse(category._is_matching_partner(order))
        self.assertFalse(category._is_applicable_for(order))

    def test_mismatch_error_names_the_failing_criterion(self):
        self._make_category(
            order_approval_mode="amount",
            order_amount_min=1000.0,
            order_partner_ids=[Command.set(self.other_vendor.ids)],
        )
        order = self._make_order(price=5000.0)
        with self.assertRaises(UserError) as caught:
            order._get_approval_category()
        message = str(caught.exception)
        self.assertIn("failed on", message)
        self.assertIn("partner", message)

    def test_open_ended_band_matches_above_the_minimum(self):
        category = self._make_category(
            order_approval_mode="amount",
            order_amount_min=1000.0,
            order_amount_max=0.0,
        )
        self.assertTrue(category._is_applicable_for(self._make_order(price=57500.0)))
