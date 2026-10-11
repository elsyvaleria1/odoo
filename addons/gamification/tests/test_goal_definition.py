from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import common


class TestGoalDefinition(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(
            patch(
                "odoo.addons.mail.models.mixin_mail_thread.MixinMailThread"
                "._notify_thread",
                lambda *args, **kwargs: [],
            )
        )
        cls.partner_model = cls.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )

    def _create_definition(self, vals=None):
        defaults = {
            "name": "Test Definition",
            "computation_mode": "count",
            "model_id": self.partner_model.id,
            "domain": "[]",
        }
        if vals:
            defaults.update(vals)
        return self.env["gamification.goal.definition"].create(defaults)

    def test_check_domain_validity_invalid(self):
        with self.assertRaises(UserError):
            self._create_definition({"domain": "not a valid domain"})

    def test_check_domain_validity_valid(self):
        definition = self._create_definition(
            {
                "domain": "[('active', '=', True)]",
            }
        )
        self.assertTrue(definition.id, "Definition should be created successfully")

    def test_compute_full_suffix_without_monetary(self):
        definition = self._create_definition(
            {
                "suffix": "tasks",
                "monetary": False,
                "computation_mode": "manually",
            }
        )
        self.assertEqual(definition.full_suffix, "tasks")

    def test_compute_full_suffix_with_monetary(self):
        definition = self._create_definition(
            {
                "suffix": "tasks",
                "monetary": False,
                "computation_mode": "manually",
            }
        )
        self.assertEqual(definition.full_suffix, "tasks")

        definition.monetary = True
        currency_symbol = self.env.company.currency_id.symbol or "¤"
        self.assertIn(currency_symbol, definition.full_suffix)
        self.assertIn("tasks", definition.full_suffix)
        self.assertEqual(definition.full_suffix, f"{currency_symbol} tasks")

    def test_compute_full_suffix_recomputes_across_company_context(self):
        other_currency = self.env["res.currency"].create(
            {"name": "XTS", "symbol": "X$"}
        )
        other_company = self.env["res.company"].create(
            {"name": "Other Currency Co", "currency_id": other_currency.id}
        )
        self.env.user.write({"company_ids": [(4, other_company.id)]})
        definition = self._create_definition(
            {
                "suffix": "tasks",
                "monetary": True,
                "computation_mode": "manually",
            }
        )
        base_symbol = self.env.company.currency_id.symbol or "¤"
        suffix_base = definition.with_context(
            allowed_company_ids=[self.env.company.id]
        ).full_suffix
        self.assertIn(base_symbol, suffix_base)

        suffix_other = definition.with_context(
            allowed_company_ids=[other_company.id]
        ).full_suffix
        self.assertIn(
            "X$",
            suffix_other,
            "full_suffix should reflect the other company's currency symbol,"
            " not stay cached on the first company read",
        )
