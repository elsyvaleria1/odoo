from unittest.mock import MagicMock, patch

from odoo import Command, fields
from odoo.exceptions import RedirectWarning
from odoo.libs.guarded_http import GuardedSession
from odoo.tests import tagged

from odoo.addons.account_online_synchronization.tests.common import (
    AccountOnlineSynchronizationCommon,
)
from odoo.addons.base.models.res_partner_bank_account import sanitize_account_number


@tagged("post_install", "-at_install")
class TestSynchStatementCreation(AccountOnlineSynchronizationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.account = cls.env["account.account"].create(
            {
                "name": "Fixed Asset Account",
                "code": "AA",
                "account_type": "asset_fixed",
            }
        )

    def test_creation_initial_sync_statement(self):
        transactions = self._create_online_transactions(["2016-01-01", "2016-01-03"])
        self.account_online_account.balance = 1000
        self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )
        statement_lines = self.env["account.bank.statement.line"].search(
            [("journal_id", "=", self.euro_bank_journal.id)]
        )
        self.assertEqual(
            len(statement_lines),
            2,
            "Should have created 2 statement lines for the transactions",
        )

        statement = self.env["account.bank.statement"].search(
            [("journal_id", "=", self.euro_bank_journal.id)]
        )
        self.assertEqual(
            len(statement.line_ids),
            1,
            "Should have created an opening bank statement with exactly one statement line",
        )
        self.assertEqual(
            statement.balance_start,
            980.0,
            "Opening Bank statement should have starting balance 980.0",
        )

        transactions = self._create_online_transactions(["2016-01-05"])
        self.account_online_account.balance = 2000
        self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )
        created_st_lines = self.BankStatementLine.search(
            [("journal_id", "=", self.euro_bank_journal.id)], order="internal_index asc"
        )
        self.assertRecordValues(
            created_st_lines,
            [
                {"date": fields.Date.from_string("2016-01-01"), "amount": 10.0},
                {"date": fields.Date.from_string("2016-01-03"), "amount": 10.0},
                {"date": fields.Date.from_string("2016-01-05"), "amount": 10.0},
            ],
        )

    def test_creation_initial_sync_statement_bis(self):
        transactions = self._create_online_transactions(["2016-01-01", "2016-01-03"])
        self.account_online_account.balance = 20
        self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )
        created_st_lines = self.BankStatementLine.search(
            [("journal_id", "=", self.euro_bank_journal.id)], order="internal_index asc"
        )
        self.assertRecordValues(
            created_st_lines,
            [
                {"date": fields.Date.from_string("2016-01-01"), "amount": 10.0},
                {"date": fields.Date.from_string("2016-01-03"), "amount": 10.0},
            ],
        )

    def test_creation_initial_sync_statement_invert_sign(self):
        self.account_online_account.balance = -20
        self.account_online_account.inverse_transaction_sign = True
        self.account_online_account.inverse_balance_sign = True
        transactions = self._create_online_transactions(["2016-01-01", "2016-01-03"])
        self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )
        created_st_lines = self.BankStatementLine.search(
            [("journal_id", "=", self.euro_bank_journal.id)], order="internal_index asc"
        )
        self.assertEqual(
            len(created_st_lines),
            2,
            "Should have created two bank statement lines for the synchronization",
        )
        transactions = self._create_online_transactions(["2016-01-05"])
        self.account_online_account.balance = -30
        self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )
        created_st_lines = self.BankStatementLine.search(
            [("journal_id", "=", self.euro_bank_journal.id)], order="internal_index asc"
        )
        self.assertRecordValues(
            created_st_lines,
            [
                {"date": fields.Date.from_string("2016-01-01"), "amount": -10.0},
                {"date": fields.Date.from_string("2016-01-03"), "amount": -10.0},
                {"date": fields.Date.from_string("2016-01-05"), "amount": -10.0},
            ],
        )

    @patch(
        "odoo.addons.account_online_synchronization.models.account_online.AccountOnlineLink._get_transactions"
    )
    @patch(
        "odoo.addons.account_online_synchronization.models.account_online.AccountOnlineLink._update_connection_status"
    )
    def test_automatic_journal_assignment(
        self, patched_update_connection_status, patched_fetch_transactions
    ):
        def create_online_account(name, link_id, iban, currency_id):
            return self.env["account.online.account"].create(
                {
                    "name": name,
                    "account_online_link_id": link_id,
                    "account_number": iban,
                    "currency_id": currency_id,
                }
            )

        def create_bank_account(account_number, partner_id):
            return self.env["res.partner.bank.account"].create(
                {
                    "acc_number": account_number,
                    "partner_id": partner_id,
                }
            )

        def create_journal(
            name, journal_type, code, currency_id=False, bank_account_id=False
        ):
            return self.env["account.journal"].create(
                {
                    "name": name,
                    "type": journal_type,
                    "code": code,
                    "currency_id": currency_id,
                    "bank_account_id": bank_account_id,
                }
            )

        bank_account_1 = create_bank_account(
            "BE48485444456727", self.company_data["company"].partner_id.id
        )
        bank_account_2 = create_bank_account(
            "BE23798242487491", self.company_data["company"].partner_id.id
        )

        bank_journal_with_account_gol = create_journal(
            "Bank with account", "bank", "BJWA1", self.other_currency.id
        )
        bank_journal_with_account_usd = create_journal(
            "Bank with account USD",
            "bank",
            "BJWA3",
            self.env.ref("base.USD").id,
            bank_account_2.id,
        )

        online_account_1 = create_online_account(
            "OnlineAccount1",
            self.account_online_link.id,
            "BE48485444456727",
            self.other_currency.id,
        )
        online_account_2 = create_online_account(
            "OnlineAccount2",
            self.account_online_link.id,
            "BE61954856342317",
            self.other_currency.id,
        )
        online_account_3 = create_online_account(
            "OnlineAccount3",
            self.account_online_link.id,
            "BE23798242487495",
            self.other_currency.id,
        )

        patched_fetch_transactions.return_value = True
        patched_update_connection_status.return_value = {
            "consent_expiring_date": None,
            "is_payment_enabled": False,
            "is_payment_activated": False,
        }

        account_link_journal_wizard = self.env[
            "wizard.account.online.link.connect.account"
        ].create({"account_online_link_id": self.account_online_link.id})
        account_link_journal_wizard.with_context(
            active_model="account.journal", active_id=bank_journal_with_account_gol.id
        ).sync_now()
        self.assertEqual(
            online_account_1.id,
            bank_journal_with_account_gol.account_online_account_id.id,
            "The wizard should have linked the online account to the journal with the same account.",
        )
        self.assertEqual(
            bank_journal_with_account_gol.bank_account_id,
            bank_account_1,
            "Account should be set on the journal",
        )

        previous_number = self.env["account.journal"].search_count([])
        account_link_journal_wizard.selected_account = online_account_2
        account_link_journal_wizard.sync_now()
        actual_number = self.env["account.journal"].search_count([])
        self.assertEqual(
            actual_number, previous_number + 1, "should have created a new journal"
        )
        self.assertEqual(online_account_2.journal_ids.currency_id, self.other_currency)
        self.assertEqual(
            online_account_2.journal_ids.bank_account_id.sanitized_acc_number,
            sanitize_account_number("BE61954856342317"),
        )

        account_link_journal_wizard.selected_account = online_account_3
        account_link_journal_wizard.with_context(
            active_model="account.journal", active_id=bank_journal_with_account_usd.id
        ).sync_now()
        self.assertEqual(
            online_account_3.id,
            bank_journal_with_account_usd.account_online_account_id.id,
        )
        self.assertEqual(
            bank_journal_with_account_usd.bank_account_id,
            bank_account_2,
            "Bank Account should not have changed",
        )
        self.assertEqual(
            bank_journal_with_account_usd.currency_id,
            self.other_currency,
            "Currency should have changed",
        )

    @patch(
        "odoo.addons.account_online_synchronization.models.account_online.AccountOnlineLink._get_odoo_fin"
    )
    def test_fetch_transaction_date_start(self, patched_fetch):
        patched_fetch.return_value = {"transactions": []}
        self.account_online_account._get_transactions_from_provider()
        data = {
            "start_date": False,
            "account_id": False,
            "last_transaction_identifier": False,
            "currency_code": "EUR",
            "account_data": False,
            "include_foreign_currency": True,
        }
        patched_fetch.assert_called_with("/proxy/v2/transactions/posted", data=data)

        self.account_online_account.last_sync = "2020-03-04"
        data["start_date"] = "2020-03-04"
        self.account_online_account._get_transactions_from_provider()
        patched_fetch.assert_called_with("/proxy/v2/transactions/posted", data=data)

        transactions = self._create_online_transactions(["2016-01-01", "2016-01-03"])
        self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )
        self.account_online_account.last_sync = "2020-03-04"
        data["start_date"] = "2016-01-03"
        data["last_transaction_identifier"] = "2"
        self.account_online_account._get_transactions_from_provider()
        patched_fetch.assert_called_with("/proxy/v2/transactions/posted", data=data)

    def test_multiple_transaction_identifier_fetched(self):
        transactions = self._create_online_transactions(["2016-01-01", "2016-01-03"])
        transactions.append(transactions[0])
        self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )
        bnk_stmt_lines = self.BankStatementLine.search(
            [
                ("online_transaction_identifier", "!=", False),
                ("journal_id", "=", self.euro_bank_journal.id),
            ]
        )
        self.assertEqual(len(bnk_stmt_lines), 2, "Should only have created two lines")

    @patch(
        "odoo.addons.account_online_synchronization.models.account_online.AccountOnlineLink._get_odoo_fin"
    )
    def test_fetch_transactions_reauth(self, patched_refresh):
        patched_refresh.side_effect = [
            {
                "success": False,
                "code": 300,
                "data": {"mode": "updateCredentials"},
            },
            {
                "access_token": "open_sesame",
            },
        ]
        self.account_online_account.account_online_link_id.state = "connected"
        res = self.account_online_account.account_online_link_id._get_transactions()
        self.assertTrue(
            "account_online_identifier" in res.get("params", {}).get("includeParam", {})
        )

    def test_duplicate_transaction_date_amount_account(self):
        transactions = self._create_online_transactions(
            [
                "2024-01-01",
                "2024-01-01",
                "2024-01-02",
                "2024-01-02",
                "2024-01-02",
            ]
        )
        bsls = self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )
        self.env.flush_all()
        duplicate_transactions = self.euro_bank_journal._get_duplicate_transactions(
            fields.Date.to_date("2000-01-01")
        )
        group_1 = bsls.filtered(
            lambda bsl: bsl.date == fields.Date.from_string("2024-01-01")
        ).ids
        group_2 = bsls.filtered(
            lambda bsl: bsl.date == fields.Date.from_string("2024-01-02")
        ).ids

        self.assertEqual(duplicate_transactions, [group_1, group_2])

        has_duplicate_transactions = self.euro_bank_journal._has_duplicate_transactions(
            fields.Date.to_date("2000-01-01")
        )
        self.assertTrue(
            has_duplicate_transactions is True
        )

    def test_duplicate_transaction_online_transaction_identifier(self):
        transactions = self._create_online_transactions(
            ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        )
        bsls = self.BankStatementLine._online_sync_bank_statement(
            transactions, self.account_online_account
        )

        group_1, group_2 = [], []
        for bsl in bsls:
            if bsl.payment_ref in ("transaction_1", "transaction_2"):
                group_1.append(bsl.id)
                bsl.online_transaction_identifier = "same_oti_1"
            if bsl.payment_ref in ("transaction_3, transaction_4, transaction_5"):
                group_2.append(bsl.id)
                bsl.online_transaction_identifier = "same_oti_2"

        self.env.flush_all()
        duplicate_transactions = self.euro_bank_journal._get_duplicate_transactions(
            fields.Date.to_date("2000-01-01")
        )
        self.assertEqual(duplicate_transactions, [group_1, group_2])

    @patch.object(GuardedSession, "request")
    def test_fetch_receive_error_message(self, patched_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": {
                "code": 400,
                "message": "Shit Happened",
                "data": {
                    "exception_type": "random",
                    "message": "This kind of things can happen.",
                    "error_reference": "abc123",
                    "provider_type": "theonlyone",
                    "redirect_warning_url": "odoo_support",
                },
            },
        }
        patched_request.return_value = mock_response

        generated_url = "https://www.odoo.com/help?stage=bank_sync&summary=Bank+sync+error+ref%3A+abc123+-+Provider%3A+theonlyone+-+Client+ID%3A+client_id_1&description=ClientID%3A+client_id_1%0AInstitution%3A+Test+Bank%0AError+Reference%3A+abc123%0AError+Message%3A+This+kind+of+things+can+happen.%0A"
        return_act_url = {"type": "ir.actions.act_url", "url": generated_url}
        body_generated_url = generated_url.replace(
            "&", "&amp;"
        )
        message_body = f"""<p>This kind of things can happen.

If you've already opened a ticket for this issue, don't report it again: a support agent will contact you shortly.<br>You can contact Odoo support <a href=\"{body_generated_url}\">Here</a></p>"""

        self.env.invalidate_all()
        with self.sync_env_with_side_cursors(), self.env.registry.cursor() as test_cr:
            test_env = self.env(cr=test_cr)
            test_link_account = self.account_online_link.with_env(test_env)
            test_link_account.state = "connected"

            try:
                test_link_account._get_odoo_fin("/testthisurl")
            except RedirectWarning as exception:
                self.assertEqual(
                    exception.args[0],
                    "This kind of things can happen.\n\nIf you've already opened a ticket for this issue, don't report it again: a support agent will contact you shortly.",
                )
                self.assertEqual(exception.args[1], return_act_url)
                self.assertEqual(exception.args[2], "Report issue")
            else:
                self.fail("Expected RedirectWarning not raised")
            self.assertEqual(test_link_account.message_ids[0].body, message_body)

    def test_account_online_link_having_journal_ids(self):
        online_link = self.env["account.online.link"].create(
            {
                "name": "My New Bank connection",
            }
        )
        online_accounts = self.env["account.online.account"].create(
            [
                {
                    "name": "Account 1",
                    "account_online_link_id": online_link.id,
                    "journal_ids": [
                        Command.create(
                            {
                                "name": "Account 1",
                                "code": "BK1",
                                "type": "bank",
                            }
                        )
                    ],
                },
                {
                    "name": "Account 2",
                    "account_online_link_id": online_link.id,
                    "journal_ids": [
                        Command.create(
                            {
                                "name": "Account 2",
                                "code": "BK2",
                                "type": "bank",
                            }
                        )
                    ],
                },
            ]
        )
        self.assertEqual(online_link.account_online_account_ids, online_accounts)
        self.assertEqual(
            len(online_link.journal_ids), 2
        )
