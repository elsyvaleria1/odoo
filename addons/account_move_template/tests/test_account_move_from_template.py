from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccountMoveFromTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.exact_account = cls.env["account.account"].create(
            {
                "name": "Exact Expense",
                "code": "TPBM42",
                "account_type": "expense",
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.prefix_account = cls.env["account.account"].create(
            {
                "name": "Prefix Expense",
                "code": "TPBM99X",
                "account_type": "expense",
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.purchase_journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", cls.company.id)],
            limit=1,
        )
        if not cls.purchase_journal:
            cls.purchase_journal = cls.env["account.journal"].create(
                {
                    "name": "Test Purchase Journal AMFT",
                    "code": "TPBMPJ",
                    "type": "purchase",
                    "company_id": cls.company.id,
                }
            )
        cls.move = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "journal_id": cls.purchase_journal.id,
                "company_id": cls.company.id,
            }
        )

    def _create_template_line(self, **overrides):
        values = {
            "sequence": 10,
            "name": "Line",
            "account_code": "TPBM42",
            "balance": 100.0,
        }
        values.update(overrides)
        template = self.env["account.move.template"].create(
            {
                "name": f"Template {overrides.get('account_code', 'TPBM42')}",
                "journal_code": self.purchase_journal.code,
                "move_type": "in_invoice",
                "company_id": self.company.id,
                "line_ids": [Command.create(values)],
            }
        )
        return template.line_ids[0]

    def test_exact_code_resolves_active_account(self):
        line = self._create_template_line(account_code="TPBM42")
        vals = self.move._prepare_move_line_from_template(line)
        self.assertEqual(vals["account_id"], self.exact_account.id)

    def test_prefix_fallback_when_no_exact_match(self):
        line = self._create_template_line(
            account_code="TPBM99",
            name="Prefix line",
        )
        vals = self.move._prepare_move_line_from_template(line)
        self.assertEqual(vals["account_id"], self.prefix_account.id)

    def test_archived_account_is_ignored(self):
        line = self._create_template_line(account_code="TPBM42")
        self.exact_account.action_archive()
        try:
            vals = self.move._prepare_move_line_from_template(line)
            self.assertFalse(vals["account_id"])
        finally:
            self.exact_account.action_unarchive()
