from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestWizardDefaults(AutomationAccountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["wizard.account.bank.statement.line.start.automation"]
        cls.default_fields = [
            "st_line_id",
            "partner_id",
            "reference",
            "amount",
            "currency_id",
            "date",
            "company_ids",
        ]

    def _make_statement_line(self, amount, ref):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal_bank.id,
                "date": "2026-08-21",
                "payment_ref": ref,
                "partner_id": self.partner.id,
                "amount": amount,
            },
        )

    def _defaults_for(self, active_id):
        return self.Wizard.with_context(
            active_model="account.bank.statement.line",
            active_id=active_id,
        ).default_get(self.default_fields)

    def test_a_deleted_statement_line_opens_the_dialog_with_plain_defaults(self):
        st_line = self._make_statement_line(100.0, "To be deleted")
        stale_id = st_line.id
        st_line.unlink()

        defaults = self._defaults_for(stale_id)

        self.assertFalse(defaults.get("st_line_id"))

    def test_an_absent_statement_line_id_opens_the_dialog(self):
        defaults = self._defaults_for(2147483000)

        self.assertFalse(defaults.get("st_line_id"))

    def test_a_live_statement_line_still_fills_the_defaults(self):
        st_line = self._make_statement_line(250.0, "Inbound line")

        defaults = self._defaults_for(st_line.id)

        self.assertEqual(defaults["st_line_id"], st_line.id)
        self.assertEqual(defaults["partner_id"], self.partner.id)
        self.assertEqual(defaults["reference"], "Inbound line")
        self.assertEqual(defaults["amount"], 250.0)

    def test_the_amount_is_absolute_for_an_outbound_line(self):
        outbound = self._make_statement_line(-850.0, "Outbound line")

        defaults = self._defaults_for(outbound.id)

        self.assertEqual(defaults["amount"], 850.0)

    def test_no_direction_field_exists_to_carry_the_sign(self):
        for name in ("payment_type", "move_type", "direction", "sign"):
            self.assertNotIn(name, self.Wizard._fields)
