from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestResConfigSettings(TransactionCase):
    def test_action_opens_the_purchase_categories_of_the_company(self):
        settings = self.env["res.config.settings"].create({})

        action = settings.action_view_po_approval_categories()

        self.assertEqual(action["res_model"], "approval.category")
        self.assertIn(("approval_type", "=", "purchase"), action["domain"])
        self.assertIn(
            ("company_id", "in", (self.env.company.id, False)),
            action["domain"],
        )
        self.assertEqual(action["context"]["default_approval_type"], "purchase")
        self.assertEqual(
            action["context"]["default_company_id"],
            self.env.company.id,
        )

        categories = self.env["approval.category"].search(action["domain"])

        self.assertTrue(
            all(category.approval_type == "purchase" for category in categories),
            "the domain must not leak categories of another approval type",
        )

    def test_action_shows_the_global_categories_the_matcher_uses(self):
        global_category = self.env["approval.category"].create(
            {
                "name": "Global Purchase Category",
                "approval_type": "purchase",
                "company_id": False,
            },
        )
        settings = self.env["res.config.settings"].create({})

        listed = self.env["approval.category"].search(
            settings.action_view_po_approval_categories()["domain"],
        )

        self.assertIn(global_category, listed)

        order = self.env["purchase.order"].new({"company_id": self.env.company.id})
        matched = self.env["approval.category"].search(
            order._get_domain_approval_category(),
        )

        self.assertIn(
            global_category,
            matched,
            "the matcher considers it, so the settings list must show it",
        )

    def test_action_still_hides_another_companys_categories(self):
        other_company = self.env["res.company"].create({"name": "Other Co"})
        foreign_category = self.env["approval.category"].create(
            {
                "name": "Foreign Purchase Category",
                "approval_type": "purchase",
                "company_id": other_company.id,
            },
        )
        settings = self.env["res.config.settings"].create({})

        listed = self.env["approval.category"].search(
            settings.action_view_po_approval_categories()["domain"],
        )

        self.assertNotIn(
            foreign_category,
            listed,
            "widening to global must not widen to every company",
        )

    def test_the_company_settings_are_reachable_through_the_wizard(self):
        settings = self.env["res.config.settings"].create({})

        settings.po_validation_level = "module_approval"
        settings.po_rate_limit_count = 7
        settings.execute()

        self.assertEqual(self.env.company.po_validation_level, "module_approval")
        self.assertEqual(self.env.company.po_rate_limit_count, 7)

    def test_a_zero_rate_limit_is_refused_instead_of_being_substituted(self):
        company = self.env.company
        company.po_rate_limit_enabled = True

        for field_name in ("po_rate_limit_hours", "po_rate_limit_count"):
            with self.subTest(field=field_name), self.assertRaises(ValidationError):
                company.write({field_name: 0})

        with self.assertRaises(ValidationError):
            company.write({"po_rate_limit_amount": 0.0})

    def test_a_negative_rate_limit_is_refused(self):
        company = self.env.company
        company.po_rate_limit_enabled = True

        with self.assertRaises(ValidationError):
            company.write({"po_rate_limit_count": -1})

    def test_disabling_the_limiter_frees_the_three_knobs(self):
        company = self.env.company

        company.write(
            {
                "po_rate_limit_enabled": False,
                "po_rate_limit_hours": 0,
                "po_rate_limit_count": 0,
                "po_rate_limit_amount": 0.0,
            },
        )

        self.assertEqual(company.po_rate_limit_count, 0)

    def test_enabling_the_limiter_over_stored_zeros_is_refused(self):
        company = self.env.company
        company.write(
            {
                "po_rate_limit_enabled": False,
                "po_rate_limit_count": 0,
            },
        )

        with self.assertRaises(ValidationError):
            company.po_rate_limit_enabled = True

    def test_the_configured_limits_reach_the_rate_limiter_unchanged(self):
        company = self.env.company
        company.write(
            {
                "po_rate_limit_enabled": True,
                "po_rate_limit_hours": 12,
                "po_rate_limit_count": 2,
                "po_rate_limit_amount": 500.0,
            },
        )
        seen = {}
        order = self.env["purchase.order"].new({"company_id": company.id})

        def spy(_self, **kwargs):
            seen.update(kwargs)
            return False

        with patch.object(type(order), "_approval_rate_limit_exceeded", spy):
            order._check_rate_limit_exceeded()

        self.assertEqual(seen["hours"], 12)
        self.assertEqual(seen["max_count"], 2)
        self.assertEqual(seen["max_amount"], 500.0)
