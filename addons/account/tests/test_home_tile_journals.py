from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestHomeTileJournals(AccountTestInvoicingCommon):
    def _row(self, journal):
        data = self.env["home.tile"].get_tiles(
            [{"id": "journals_1", "type": "journals"}]
        )["journals_1"]["data"]
        row = next((r for r in data["journals"] if r["id"] == journal.id), None)
        return data, row or {"to_validate": 0, "late": 0, "to_reconcile": 0}

    def test_the_accounting_tile_counts_what_waits_in_each_journal(self):
        journal = self.company_data["default_journal_sale"]
        before, row_before = self._row(journal)
        self.init_invoice("out_invoice", amounts=[100.0])
        self.init_invoice(
            "out_invoice", invoice_date="2020-01-01", amounts=[100.0], post=True
        )
        after, row = self._row(journal)
        self.assertEqual(row["to_validate"] - row_before["to_validate"], 1)
        self.assertEqual(row["late"] - row_before["late"], 1)
        self.assertEqual(after["to_validate"] - before["to_validate"], 1)
        self.assertEqual(after["late"] - before["late"], 1)
        self.assertEqual(row["type"], "sale")

    def test_only_who_sees_the_accounting_dashboard_is_offered_the_tile(self):
        billing = new_test_user(
            self.env, login="tile_billing", groups="account.group_account_invoice"
        )
        accountant = new_test_user(
            self.env, login="tile_accountant", groups="account.group_account_basic"
        )
        tiles = self.env["home.tile"]
        self.assertTrue(tiles.with_user(billing).env["account.move"].has_access("read"))
        self.assertNotIn("journals", tiles.with_user(billing).get_tile_types())
        self.assertEqual(
            tiles.with_user(billing).get_tiles(
                [{"id": "journals_1", "type": "journals"}]
            ),
            {"journals_1": {"error": "unavailable"}},
        )
        self.assertIn("journals", tiles.with_user(accountant).get_tile_types())

    def test_the_journals_tile_keeps_its_statement_count(self):
        request = [{"id": "journals_1", "type": "journals"}]
        self.env["home.tile"].get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(10):
            self.env["home.tile"].get_tiles(request)

    def test_the_tile_counts_what_the_journal_dashboard_counts(self):
        self.init_invoice("out_invoice", amounts=[100.0])
        self.init_invoice(
            "out_invoice", invoice_date="2020-01-01", amounts=[100.0], post=True
        )
        self.init_invoice("in_invoice", amounts=[50.0])
        journals = self.env["account.journal"].search(
            [("show_on_dashboard", "=", True)]
        )
        dashboard = journals._get_journal_dashboard_data_batched()
        counts = journals._get_attention_counts()
        for journal in journals:
            with self.subTest(journal=journal.name):
                self.assertEqual(
                    counts[journal.id],
                    {
                        "to_reconcile": dashboard[journal.id].get(
                            "number_to_reconcile", 0
                        ),
                        "to_validate": dashboard[journal.id].get("number_draft", 0),
                        "late": dashboard[journal.id].get("number_late", 0),
                    },
                )
