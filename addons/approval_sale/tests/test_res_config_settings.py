from odoo.tests import tagged
from odoo.tests.common import TransactionCase

RATE_LIMIT_FIELDS = (
    "so_rate_limit_enabled",
    "so_rate_limit_hours",
    "so_rate_limit_count",
    "so_rate_limit_amount",
)


@tagged("post_install", "-at_install")
class TestResConfigSettings(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

    def _settings(self, **values):
        return self.env["res.config.settings"].create(
            {"company_id": self.company.id, **values},
        )

    def test_the_rate_limit_fallback_is_the_company_default(self):
        company = self.env["res.company"]
        self.assertEqual(
            self.env["sale.order"]._get_approval_rate_limit_fallback(),
            company._fields["so_rate_limit_amount"].default(company),
            "the fallback and the field default are one policy; they must not "
            "be able to drift apart in two files",
        )

    def test_the_categories_action_shows_the_shipped_global_categories(self):
        shipped = self.env.ref(
            "approval_sale.approval_category_sale_order",
        ) | self.env.ref("approval_sale.approval_category_sale_request")
        self.assertFalse(
            shipped.company_id,
            "the shipped categories are global; if this ever changes, the "
            "action-domain assertion below loses its point",
        )

        action = self._settings().action_view_so_approval_categories()
        visible = self.env["approval.category"].search(action["domain"])

        self.assertTrue(
            shipped <= visible,
            "the Settings button must show the shipped global categories; a "
            "company_id '=' filter hides every category the module ships",
        )

    def test_the_rate_limit_fields_are_on_the_wizard(self):
        for name in RATE_LIMIT_FIELDS:
            self.assertIn(name, self.env["res.config.settings"]._fields)

    def test_the_rate_limit_fields_are_rendered_somewhere(self):
        view = self.env.ref(
            "approval_sale.res_config_settings_view_form_approval_sale",
        )
        for name in RATE_LIMIT_FIELDS:
            self.assertIn(name, view.arch_db)

    def test_writing_the_settings_reaches_the_company(self):
        settings = self._settings(
            so_rate_limit_enabled=True,
            so_rate_limit_hours=12,
            so_rate_limit_count=9,
            so_rate_limit_amount=1234.0,
        )
        settings.execute()

        self.assertTrue(self.company.so_rate_limit_enabled)
        self.assertEqual(self.company.so_rate_limit_hours, 12)
        self.assertEqual(self.company.so_rate_limit_count, 9)
        self.assertEqual(self.company.so_rate_limit_amount, 1234.0)

    def test_disabling_the_limiter_reaches_the_company(self):
        self.company.so_rate_limit_enabled = True

        settings = self._settings(so_rate_limit_enabled=False)
        settings.execute()

        self.assertFalse(self.company.so_rate_limit_enabled)

    def test_the_settings_read_back_the_company_values(self):
        self.company.write(
            {
                "so_rate_limit_enabled": True,
                "so_rate_limit_hours": 48,
                "so_rate_limit_count": 3,
                "so_rate_limit_amount": 500.0,
            },
        )

        settings = self._settings()

        self.assertTrue(settings.so_rate_limit_enabled)
        self.assertEqual(settings.so_rate_limit_hours, 48)
        self.assertEqual(settings.so_rate_limit_count, 3)
        self.assertEqual(settings.so_rate_limit_amount, 500.0)

    def test_the_existing_validation_settings_still_round_trip(self):
        settings = self._settings(
            so_validation_level="module_approval",
            so_validation_amount=7500.0,
            so_auto_confirm_on_approval=False,
        )
        settings.execute()

        self.assertEqual(self.company.so_validation_level, "module_approval")
        self.assertEqual(self.company.so_validation_amount, 7500.0)
        self.assertFalse(self.company.so_auto_confirm_on_approval)

    def test_the_category_shortcut_targets_sale_categories(self):
        action = self._settings().action_view_so_approval_categories()

        self.assertEqual(action["res_model"], "approval.category")
        self.assertIn(("approval_type", "=", "sale"), action["domain"])

    def test_the_pending_shortcut_targets_pending_orders(self):
        action = self._settings().action_view_pending_so_approvals()

        self.assertEqual(action["res_model"], "sale.order")
        self.assertIn(("approval_state", "=", "pending"), action["domain"])
