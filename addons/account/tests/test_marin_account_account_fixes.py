from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestMarinAccountAccountFixes(AccountTestInvoicingCommon):
    def test_display_name_code_does_not_leak_between_users(self):
        account = self.env["account.account"].search(
            [
                *self.env["account.account"]._check_company_domain(self.env.company),
                ("code", "!=", False),
            ],
            limit=1,
        )
        self.assertTrue(account, "precondition: the company has at least one account")
        code = account.with_company(self.env.company).code

        privileged = new_test_user(
            self.env,
            login="marin_acc_priv",
            groups="account.group_account_readonly",
            company_id=self.env.company.id,
        )
        plain = new_test_user(
            self.env,
            login="marin_acc_plain",
            groups="base.group_user",
            company_id=self.env.company.id,
        )
        self.assertTrue(privileged.has_group("account.group_account_readonly"))
        self.assertFalse(plain.has_group("account.group_account_readonly"))

        context = {"formatted_display_name": True}
        privileged_name = (
            account.with_user(privileged).with_context(**context).display_name
        )
        plain_name = account.with_user(plain).with_context(**context).display_name

        self.assertIn(
            code, privileged_name, "the group that may see the code still sees it"
        )
        self.assertNotIn(
            code,
            plain_name,
            "a user without the group must not be served the privileged user's name",
        )

    def test_liquidity_lines_show_their_residual(self):
        bank_account = self.company_data["default_journal_bank"].default_account_id
        credit_card_account = self.env["account.account"].create(
            {
                "name": "Residual Card",
                "code": "190601",
                "account_type": "liability_credit_card",
            }
        )
        current_account = self.env["account.account"].create(
            {
                "name": "Residual Current",
                "code": "190602",
                "account_type": "asset_current",
            }
        )
        self.assertFalse(any((bank_account | credit_card_account).mapped("reconcile")))
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2017-01-01",
                "line_ids": [
                    Command.create({"account_id": bank_account.id, "balance": 100.0}),
                    Command.create(
                        {"account_id": credit_card_account.id, "balance": -60.0}
                    ),
                    Command.create(
                        {"account_id": current_account.id, "balance": -40.0}
                    ),
                ],
            }
        )
        self.assertEqual(
            move.line_ids.filtered("is_account_reconcile").account_id,
            bank_account | credit_card_account,
        )


@tagged("post_install", "-at_install")
class TestMarinAccountAccountMultiCompany(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()
        cls.company_1 = cls.company_data["company"]
        cls.company_2 = cls.company_data_2["company"]
        cls.both_companies = cls.company_1 | cls.company_2

    def _accounts(self):
        return self.env["account.account"].with_context(
            allowed_company_ids=self.both_companies.ids
        )

    def _code_mapping_commands(self, code):
        return [
            Command.create({"company_id": company.id, "code": code})
            for company in self.both_companies
        ]

    def test_create_returns_records_in_input_order_across_companies(self):
        vals_list = [
            {
                "name": "Order A",
                "code": "190101",
                "company_ids": [Command.set(self.company_1.ids)],
            },
            {
                "name": "Order B",
                "code": "190102",
                "company_ids": [Command.set(self.company_2.ids)],
            },
            {
                "name": "Order C",
                "prefix": "1909",
                "code_digits": 6,
                "company_ids": [Command.set(self.company_1.ids)],
            },
        ]
        accounts = self._accounts().create(vals_list)

        self.assertEqual(accounts.mapped("name"), ["Order A", "Order B", "Order C"])
        self.assertEqual(
            [account.company_ids for account in accounts],
            [self.company_1, self.company_2, self.company_1],
        )
        self.assertEqual(
            (vals_list[2].get("prefix"), vals_list[2].get("code_digits")),
            ("1909", 6),
            "create must not consume the caller's vals",
        )
        self.assertNotIn("code", vals_list[2])

    def test_prefix_code_skips_codes_given_in_the_same_batch(self):
        accounts = self._accounts().create(
            [
                {"name": "Prefixed", "prefix": "1905", "code_digits": 6},
                {"name": "Explicit", "code": "190501"},
            ]
        )
        self.assertEqual(accounts.mapped("code"), ["190502", "190501"])

    def test_prefix_code_skips_codes_of_the_same_company_spelled_otherwise(self):
        Account = self._accounts()
        accounts = Account.create(
            [
                {"name": "Prefixed", "prefix": "1906", "code_digits": 6},
                {
                    "name": "Explicit",
                    "code": "190601",
                    "company_ids": [Command.set(Account.env.company.ids)],
                },
            ]
        )
        self.assertEqual(accounts.mapped("code"), ["190602", "190601"])

    def test_copy_of_mixed_company_recordset_pairs_sources_with_copies(self):
        accounts = self._accounts().create(
            [
                {
                    "name": "Copy A",
                    "code": "190201",
                    "company_ids": [Command.set(self.company_1.ids)],
                },
                {
                    "name": "Copy B",
                    "code": "190202",
                    "company_ids": [Command.set(self.company_2.ids)],
                },
                {
                    "name": "Copy C",
                    "code": "190203",
                    "company_ids": [Command.set(self.company_1.ids)],
                },
            ]
        )
        copies = accounts.copy()
        self.assertEqual(
            copies.mapped("name"),
            ["Copy A (copy)", "Copy B (copy)", "Copy C (copy)"],
        )

    def test_code_mapping_command_without_code_is_accepted(self):
        branch = self.env["res.company"].create(
            {"name": "Mapping branch", "parent_id": self.company_1.id}
        )
        account = (
            self.env["account.account"]
            .with_context(allowed_company_ids=(self.company_1 | branch).ids)
            .create(
                {
                    "name": "Mapping without code",
                    "code": "190301",
                    "company_ids": [Command.set((self.company_1 | branch).ids)],
                    "code_mapping_ids": [Command.create({"company_id": branch.id})],
                }
            )
        )
        self.assertEqual(account.with_company(branch).code, "190301")

    def test_root_id_follows_the_user_reading_it(self):
        account = (
            self.env["account.account"]
            .with_context(allowed_company_ids=self.company_2.ids)
            .create(
                {
                    "name": "Only in company 2",
                    "code": "190401",
                    "company_ids": [Command.set(self.company_2.ids)],
                }
            )
        )
        user_both = new_test_user(
            self.env,
            login="marin_root_both",
            groups="account.group_account_readonly",
            company_id=self.company_1.id,
            company_ids=[Command.set(self.both_companies.ids)],
        )
        user_one = new_test_user(
            self.env,
            login="marin_root_one",
            groups="account.group_account_readonly",
            company_id=self.company_1.id,
            company_ids=[Command.set(self.company_1.ids)],
        )
        account_both = account.with_user(user_both).with_company(self.company_1)
        account_one = account.with_user(user_one).with_company(self.company_1).sudo()

        self.assertEqual(account_both.placeholder_code, "190401 (company_2)")
        self.assertEqual(account_both.root_id.id, "19")
        self.assertFalse(account_one.placeholder_code)
        self.assertFalse(
            account_one.root_id,
            "root_id is derived from placeholder_code, which differs per user",
        )

    def test_a_credit_card_account_cannot_be_created_for_two_companies(self):
        with self.assertRaisesRegex(ValidationError, "cannot be shared"):
            self._accounts().create(
                {
                    "name": "Shared Credit Card",
                    "account_type": "liability_credit_card",
                    "company_ids": [Command.set(self.both_companies.ids)],
                    "code_mapping_ids": self._code_mapping_commands("190501"),
                }
            )

    def test_a_shared_account_cannot_become_a_credit_card_account(self):
        account = self._accounts().create(
            {
                "name": "Shared Current",
                "account_type": "liability_current",
                "company_ids": [Command.set(self.both_companies.ids)],
                "code_mapping_ids": self._code_mapping_commands("190502"),
            }
        )
        with self.assertRaisesRegex(ValidationError, "cannot be shared"):
            account.account_type = "liability_credit_card"

    def test_a_credit_card_account_cannot_gain_a_second_company(self):
        account = self._accounts().create(
            {
                "name": "Credit Card",
                "code": "190503",
                "account_type": "liability_credit_card",
                "company_ids": [Command.set(self.company_1.ids)],
            }
        )
        with self.assertRaisesRegex(ValidationError, "cannot be shared"):
            account.write(
                {
                    "company_ids": [Command.link(self.company_2.id)],
                    "code_mapping_ids": [
                        Command.create(
                            {"company_id": self.company_2.id, "code": "190503"}
                        )
                    ],
                }
            )

    def test_merge_wizard_leaves_out_credit_card_accounts(self):
        Account = self._accounts()
        credit_cards = Account.create(
            [
                {
                    "name": "Merge Card",
                    "code": "190504",
                    "account_type": "liability_credit_card",
                    "company_ids": [Command.set(company.ids)],
                }
                for company in self.both_companies
            ]
        )
        currents = Account.create(
            [
                {
                    "name": "Merge Current",
                    "code": "190505",
                    "account_type": "liability_current",
                    "company_ids": [Command.set(company.ids)],
                }
                for company in self.both_companies
            ]
        )
        wizard = (
            self.env["wizard.account.account.merge"]
            .with_context(
                allowed_company_ids=self.both_companies.ids,
                active_model="account.account",
                active_ids=(credit_cards | currents).ids,
            )
            .create({})
        )
        self.assertEqual(
            wizard.wizard_line_ids.filtered(
                lambda line: line.display_type == "account"
            ).account_id,
            currents,
        )


@tagged("post_install", "-at_install")
class TestMarinFiscalYearBranches(AccountTestInvoicingCommon):
    def test_branch_uses_the_root_company_fiscal_year(self):
        root = self.company_data["company"]
        branch = self.env["res.company"].create(
            {"name": "Fiscal year branch", "parent_id": root.id}
        )
        self.env["account.fiscal.year"].create(
            {
                "name": "FY 2017-2018",
                "date_from": date(2017, 3, 1),
                "date_to": date(2018, 2, 28),
                "company_id": root.id,
            }
        )
        day = date(2017, 6, 1)
        root_dates = root.compute_fiscalyear_dates(day)
        self.assertEqual(
            (root_dates["date_from"], root_dates["date_to"]),
            (date(2017, 3, 1), date(2018, 2, 28)),
        )
        by_company = (root | branch)._compute_fiscalyear_dates_by_company(day)
        self.assertEqual(
            (by_company[branch.id]["date_from"], by_company[branch.id]["date_to"]),
            (date(2017, 3, 1), date(2018, 2, 28)),
        )
        self.assertEqual(
            branch.compute_fiscalyear_dates(day)["date_to"], date(2018, 2, 28)
        )

    def test_a_branch_user_reads_the_root_fiscal_year_but_cannot_edit_it(self):
        root = self.company_data["company"]
        branch = self.env["res.company"].create(
            {"name": "Fiscal year branch only", "parent_id": root.id}
        )
        fiscal_year = self.env["account.fiscal.year"].create(
            {
                "name": "FY 2017-2018",
                "date_from": date(2017, 3, 1),
                "date_to": date(2018, 2, 28),
                "company_id": root.id,
            }
        )
        user = new_test_user(
            self.env,
            login="branch_only_manager",
            groups="account.group_account_manager",
            company_id=branch.id,
            company_ids=[Command.set(branch.ids)],
        )
        branch_env = self.env(user=user, context={"allowed_company_ids": branch.ids})

        dates = branch.with_env(branch_env).compute_fiscalyear_dates(date(2017, 6, 1))

        self.assertEqual(
            (dates["date_from"], dates["date_to"]),
            (date(2017, 3, 1), date(2018, 2, 28)),
        )
        with self.assertRaises(AccessError):
            fiscal_year.with_env(branch_env).name = "renamed by a branch"


@tagged("post_install", "-at_install")
class TestMarinSepaModuleInstall(AccountTestInvoicingCommon):
    def _installed_by(self, companies):
        requested = []

        def button_install(modules):
            requested.extend(modules.mapped("name"))

        def button_immediate_install(modules):
            raise AssertionError("tests must never install a module immediately")

        Module = type(self.env["ir.module.module"])
        with (
            patch.object(Module, "button_install", button_install),
            patch.object(Module, "button_immediate_install", button_immediate_install),
        ):
            self.env["account.chart.template"]._install_sepa_modules(companies)
        return sorted(requested)

    def test_sepa_company_requests_both_sepa_modules(self):
        company = self.env["res.company"].create(
            {"name": "SEPA company", "country_id": self.env.ref("base.be").id}
        )
        uninstalled = (
            self.env["ir.module.module"]
            .search(
                [
                    (
                        "name",
                        "in",
                        ["account_iso20022", "account_bank_statement_import_camt"],
                    ),
                    ("state", "=", "uninstalled"),
                ]
            )
            .mapped("name")
        )
        self.assertTrue(uninstalled, "precondition: a SEPA module is not installed")
        self.assertEqual(self._installed_by(company), sorted(uninstalled))

    def test_non_sepa_company_requests_nothing(self):
        company = self.env["res.company"].create(
            {"name": "Non SEPA company", "country_id": self.env.ref("base.mx").id}
        )
        self.assertEqual(self._installed_by(company), [])
