from odoo.tests.common import TransactionCase


class SpreadsheetIrModel(TransactionCase):
    def test_has_searchable_parent_not_stored(self):
        self.assertEqual(
            self.env["ir.model"].get_parent_searchability(["res.users"]),
            {"res.users": False},
        )

    def test_has_searchable_parent_stored(self):
        self.assertEqual(
            self.env["ir.model"].get_parent_searchability(["ir.ui.menu"]),
            {"ir.ui.menu": True},
        )
