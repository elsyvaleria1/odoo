from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, RedirectWarning, ValidationError
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

    def _legacy_shared_credit_card(self, code_1, code_2):
        account = self._accounts().create(
            {
                "name": "Legacy Card",
                "code": code_1,
                "account_type": "liability_credit_card",
                "company_ids": [Command.set(self.company_1.ids)],
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            "INSERT INTO account_account_res_company_rel "
            "(account_account_id, res_company_id) VALUES (%s, %s)",
            [account.id, self.company_2.id],
        )
        self.env.cr.execute(
            "UPDATE account_account "
            "SET code_store = code_store || jsonb_build_object(%s::text, %s::text) "
            "WHERE id = %s",
            [self.company_2.root_id.id, code_2, account.id],
        )
        self.env.invalidate_all()
        self.assertEqual(account.company_ids, self.both_companies)
        return account

    def test_a_legacy_shared_credit_card_account_can_be_unmerged(self):
        account = self._legacy_shared_credit_card("190506", "190507")
        move_2 = self.env["account.move"].create(
            {
                "company_id": self.company_2.id,
                "journal_id": self.company_data_2["default_journal_misc"].id,
                "line_ids": [
                    Command.create(
                        {"account_id": account.id, "debit": 0.0, "credit": 10.0}
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data_2[
                                "default_account_expense"
                            ].id,
                            "debit": 10.0,
                            "credit": 0.0,
                        }
                    ),
                ],
            }
        )

        account.with_company(self.company_1).with_context(
            allowed_company_ids=self.both_companies.ids,
            account_unmerge_confirm=True,
        ).action_unmerge()
        self.env.invalidate_all()

        split = self._accounts().search(
            [("name", "=", "Legacy Card"), ("id", "!=", account.id)]
        )
        self.assertRecordValues(
            account,
            [
                {
                    "company_ids": self.company_1.ids,
                    "code": "190506",
                    "account_type": "liability_credit_card",
                }
            ],
        )
        self.assertRecordValues(
            split.with_company(self.company_2),
            [
                {
                    "company_ids": self.company_2.ids,
                    "code": "190507",
                    "account_type": "liability_credit_card",
                }
            ],
        )
        self.assertEqual(
            move_2.line_ids.filtered(lambda line: line.credit).account_id, split
        )

    def test_a_legacy_shared_credit_card_account_is_not_duplicated_shared(self):
        account = self._legacy_shared_credit_card("190508", "190509")
        with self.assertRaisesRegex(ValidationError, "cannot be shared"):
            account.copy()

        account.with_context(
            allowed_company_ids=self.both_companies.ids,
            account_unmerge_confirm=True,
        ).action_unmerge()
        copy = account.copy()
        self.assertRecordValues(
            copy,
            [
                {
                    "company_ids": self.company_1.ids,
                    "code": "190510",
                    "name": "Legacy Card (copy)",
                }
            ],
        )

    def _accounting_manager_env(self, login):
        user = new_test_user(
            self.env,
            login=login,
            groups="account.group_account_manager",
            company_id=self.company_2.id,
            company_ids=[Command.set(self.both_companies.ids)],
        )
        return self.env(
            user=user, context={"allowed_company_ids": self.both_companies.ids}
        )

    def test_an_accounting_manager_unmerges_through_the_server_action(self):
        account = self._accounts().create(
            {
                "name": "Shared Current",
                "account_type": "asset_current",
                "company_ids": [Command.set(self.both_companies.ids)],
                "code_mapping_ids": self._code_mapping_commands("190511"),
            }
        )
        move_2 = self.env["account.move"].create(
            {
                "company_id": self.company_2.id,
                "journal_id": self.company_data_2["default_journal_misc"].id,
                "line_ids": [
                    Command.create({"account_id": account.id, "debit": 10.0}),
                    Command.create(
                        {
                            "account_id": self.company_data_2[
                                "default_account_expense"
                            ].id,
                            "credit": 10.0,
                        }
                    ),
                ],
            }
        )
        manager_env = self._accounting_manager_env("unmerge_manager")
        action = self.env.ref("account.action_unmerge_accounts").with_env(manager_env)
        context = {
            "active_model": "account.account",
            "active_ids": account.ids,
            "active_id": account.id,
        }

        with self.assertRaises(RedirectWarning) as confirmation:
            action.with_context(**context).run()
        additional_context = confirmation.exception.args[3]
        self.assertTrue(additional_context["account_unmerge_confirm"])
        result = action.with_context(**{**context, **additional_context}).run()

        self.assertEqual(result["tag"], "soft_reload")
        self.env.invalidate_all()
        split = self._accounts().search(
            [("name", "=", "Shared Current"), ("id", "!=", account.id)]
        )
        self.assertRecordValues(
            account | split,
            [
                {"company_ids": self.company_1.ids},
                {"company_ids": self.company_2.ids},
            ],
        )
        self.assertEqual(
            move_2.line_ids.filtered(lambda line: line.debit).account_id, split
        )

    def test_an_accounting_manager_merges_through_the_wizard(self):
        accounts = self._accounts().create(
            [
                {
                    "name": "Merge Current",
                    "code": "190512",
                    "account_type": "asset_current",
                    "company_ids": [Command.set(company.ids)],
                }
                for company in self.both_companies
            ]
        )
        manager_env = self._accounting_manager_env("merge_manager")
        wizard = (
            self.env["wizard.account.account.merge"]
            .with_env(manager_env)
            .with_context(active_model="account.account", active_ids=accounts.ids)
            .create({})
        )
        wizard.action_merge()
        self.assertEqual(
            accounts.exists().company_ids.sorted("id"),
            self.both_companies.sorted("id"),
        )


@tagged("post_install", "-at_install")
class TestMarinAccountAuditWithoutWorkingFile(AccountTestInvoicingCommon):
    def test_audit_fields_search_and_group_without_working_file(self):
        Account = self.env["account.account"]
        self.assertFalse(self.env.context.get("working_file_id"))
        for field_name in (
            "audit_debit",
            "audit_credit",
            "audit_balance",
            "audit_previous_balance",
            "audit_var_n_1",
        ):
            with self.subTest(field_name=field_name):
                self.assertFalse(Account.search([(field_name, ">", 0)]))
                self.assertEqual(
                    Account.search([(field_name, "=", 0)]),
                    Account.search([]),
                )
        self.assertFalse(Account.search([("audit_var_percentage", ">", 0)]))
        self.assertEqual(
            Account.search([("audit_var_percentage", "=", False)]),
            Account.search([]),
        )
        groups = Account._read_group([], ["audit_balance"], ["__count"])
        self.assertEqual(groups, [(0.0, Account.search_count([]))])


@tagged("post_install", "-at_install")
class TestMarinAccountAuditWithWorkingFile(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.audit_2024 = (
            cls.env.ref("account.default_audit_return_type")
            .with_context(
                forced_date_from=date(2024, 1, 1), forced_date_to=date(2024, 12, 31)
            )
            ._try_create_returns_for_fiscal_year(cls.env.company, False)
        )
        revenue = cls.company_data["default_account_revenue"]
        receivable = cls.company_data["default_account_receivable"]
        assets = cls.company_data["default_account_assets"]
        cls.env["account.move"].create(
            [
                {
                    "date": move_date,
                    "journal_id": cls.company_data["default_journal_misc"].id,
                    "line_ids": [
                        Command.create({"account_id": debit.id, "debit": amount}),
                        Command.create({"account_id": credit.id, "credit": amount}),
                    ],
                }
                for move_date, debit, credit, amount in (
                    ("2023-06-01", receivable, revenue, 100.0),
                    ("2023-07-01", assets, receivable, 100.0),
                    ("2024-03-01", receivable, revenue, 150.0),
                )
            ]
        ).action_post()

    def _accounts(self):
        return self.env["account.account"].with_context(
            working_file_id=self.audit_2024.id
        )

    def _computed(self, field_name):
        self.env.invalidate_all()
        accounts = self._accounts().search([])
        return {account: account[field_name] for account in accounts}

    def _assert_searches_as_computed(self, conditions, found, computed):
        for operator, value in conditions:
            match = {
                "=": lambda v, value=value: v == value,
                "!=": lambda v, value=value: v != value,
                ">": lambda v, value=value: v > value,
                ">=": lambda v, value=value: v >= value,
                "<": lambda v, value=value: v < value,
                "<=": lambda v, value=value: v <= value,
                "in": lambda v, value=value: v in value,
                "not in": lambda v, value=value: v not in value,
            }[operator]
            with self.subTest(operator=operator, value=value):
                self.assertEqual(
                    found[operator, str(value)],
                    self._accounts()
                    .browse(
                        account.id
                        for account, computed_value in computed.items()
                        if match(computed_value)
                    )
                    .sorted("id"),
                )

    def _search_all(self, field_name, conditions):
        return {
            (operator, str(value)): self._accounts()
            .search([(field_name, operator, value)])
            .sorted("id")
            for operator, value in conditions
        }

    def test_audit_status_searches_and_groups_as_it_computes(self):
        Account = self._accounts()
        unseeded = Account.create(
            {
                "name": "Opened after the audit",
                "code": "190513",
                "account_type": "expense",
            }
        )
        conditions = [
            ("=", "todo"),
            ("!=", "todo"),
            ("in", ["todo", "reviewed"]),
            ("not in", ["reviewed"]),
            ("=", False),
            ("!=", False),
        ]
        found = self._search_all("audit_status", conditions)
        groups = dict(Account._read_group([], ["audit_status"], ["__count"]))
        ordered = Account.search([], order="audit_status, id")

        computed = self._computed("audit_status")
        self.assertEqual(computed[unseeded], "todo")
        self.assertEqual(set(computed.values()), {"todo", False})
        self._assert_searches_as_computed(conditions, found, computed)
        self.assertEqual(
            groups,
            {
                value: list(computed.values()).count(value)
                for value in set(computed.values())
            },
        )
        todo = [account for account in ordered if computed[account] == "todo"]
        self.assertEqual(todo, sorted(todo, key=lambda account: account.id))
        self.assertEqual(ordered[: len(todo)].ids, [account.id for account in todo])

    def test_audit_var_percentage_searches_and_orders_as_it_computes(self):
        Account = self._accounts()
        revenue = self.company_data["default_account_revenue"]
        receivable = self.company_data["default_account_receivable"]
        assets = self.company_data["default_account_assets"]
        conditions = [
            (operator, value)
            for operator in ("=", "!=", ">", ">=", "<", "<=")
            for value in (-1.0, 0.0, 0.5, 50.0)
        ] + [
            ("in", [0.0, 0.5]),
            ("not in", [0.0, 0.5]),
            ("=", False),
            ("!=", False),
        ]
        found = self._search_all("audit_var_percentage", conditions)
        ordered = {
            direction: Account.search([], order=f"audit_var_percentage {direction}, id")
            for direction in ("asc", "desc")
        }
        groups = dict(Account._read_group([], ["audit_var_percentage"], ["__count"]))

        computed = self._computed("audit_var_percentage")
        self.assertEqual(
            [computed[account] for account in (revenue, receivable, assets)],
            [0.5, 0.0, 0.0],
        )
        self._assert_searches_as_computed(conditions, found, computed)
        for direction, records in ordered.items():
            sign = -1 if direction == "desc" else 1
            with self.subTest(direction=direction):
                self.assertEqual(
                    records,
                    Account.browse(
                        account.id
                        for account in sorted(
                            computed,
                            key=lambda account: (sign * computed[account], account.id),
                        )
                    ),
                )
        self.assertEqual(groups, {0.5: 1, 0.0: len(computed) - 1})


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
