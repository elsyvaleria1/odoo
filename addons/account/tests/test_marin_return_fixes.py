import calendar
from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.models.account_return_type import MONTHS_PER_PERIOD
from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestMarinReturnFixes(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.startClassPatcher(freeze_time("2024-01-16"))
        cls.root_company = cls.company_data["company"]
        cls.root_company.vat = "US12345671"
        cls.tax_report = cls.env["report.formula"].create(
            {
                "root_report_id": cls.env.ref("account.generic_tax_report").id,
                "name": "Marin Returns Tax Report",
            }
        )
        cls.return_type = cls.env["account.return.type"].create(
            {
                "name": "VAT Return (Marin)",
                "report_id": cls.tax_report.id,
                "default_deadline_start_date": "2024-01-01",
            }
        )

    @classmethod
    def _patch_returns_generation(cls):
        def generate_only_the_test_type(
            return_type, country_code, main_company, tax_unit=None
        ):
            cls.return_type.with_env(
                return_type.env
            )._try_create_returns_for_fiscal_year(main_company, tax_unit)

        return patch.object(
            cls.registry["account.return.type"],
            "_generate_all_returns",
            generate_only_the_test_type,
        )

    def _boundaries(self, day, start, months):
        return self.return_type._get_period_boundaries(
            self.root_company,
            day,
            override_period_months=months,
            override_start_date=start,
        )

    def test_periods_tile_the_calendar_for_every_start_day(self):
        anchors = [date(2024, 1, day) for day in range(1, 32)] + [
            date(2024, 2, 29),
            date(2024, 8, 31),
            date(2024, 11, 30),
        ]
        last_day = date(2026, 12, 31)
        for months in sorted(set(MONTHS_PER_PERIOD.values())):
            for anchor in anchors:
                with self.subTest(months=months, anchor=anchor):
                    pointer = date(2023, 1, 1)
                    while pointer <= last_day:
                        period_start, period_end = self._boundaries(
                            pointer, anchor, months
                        )
                        self.assertLessEqual(period_start, pointer)
                        self.assertLessEqual(pointer, period_end)
                        self.assertEqual(
                            (period_start.month - anchor.month) % months, 0
                        )
                        self.assertEqual(
                            period_start.day,
                            min(
                                anchor.day,
                                calendar.monthrange(
                                    period_start.year, period_start.month
                                )[1],
                            ),
                        )
                        self.assertEqual(
                            self._boundaries(period_start, anchor, months),
                            (period_start, period_end),
                        )
                        self.assertEqual(
                            self._boundaries(period_end, anchor, months),
                            (period_start, period_end),
                        )
                        if pointer != date(2023, 1, 1):
                            self.assertEqual(period_start, pointer)
                        pointer = period_end + timedelta(days=1)

    def test_month_end_start_day_does_not_overlap(self):
        anchor = date(2024, 1, 31)
        self.assertEqual(
            self._boundaries(date(2025, 1, 31), anchor, 1),
            (date(2025, 1, 31), date(2025, 2, 27)),
        )
        self.assertEqual(
            self._boundaries(date(2025, 2, 28), anchor, 1),
            (date(2025, 2, 28), date(2025, 3, 30)),
        )
        self.assertEqual(
            self._boundaries(date(2025, 3, 2), anchor, 1),
            (date(2025, 2, 28), date(2025, 3, 30)),
        )

    def test_leap_day_start_date_in_a_common_year(self):
        self.return_type.with_company(self.root_company).deadline_start_date = date(
            2024, 2, 29
        )
        self.root_company.account_config_id.account_return_periodicity = "year"
        self.assertEqual(
            self.return_type._get_period_boundaries(
                self.root_company, date(2025, 1, 10)
            ),
            (date(2024, 2, 29), date(2025, 2, 27)),
        )
        self.assertEqual(
            self.return_type._get_period_boundaries(
                self.root_company, date(2025, 6, 1)
            ),
            (date(2025, 2, 28), date(2026, 2, 27)),
        )

    def test_same_vat_sub_branch_under_a_vatless_branch_gets_no_own_returns(self):
        with self._patch_returns_generation():
            branch = self.setup_other_company(
                name="Branch without VAT", parent_id=self.root_company.id
            )["company"]
            sub_branch = self.setup_other_company(
                name="Sub-branch with the root's VAT",
                parent_id=branch.id,
                vat=self.root_company.vat,
                account_opening_date="2024-01-01",
            )["company"]
            self.root_company.account_config_id.account_opening_date = "2024-01-01"

        returns = self.env["account.return"].search(
            [("type_id", "=", self.return_type.id)]
        )
        self.assertTrue(returns)
        self.assertEqual(returns.company_id, self.root_company)
        self.assertTrue(
            all(sub_branch in tax_return.company_ids for tax_return in returns)
        )

    def test_creation_wizard_uses_the_company_the_return_is_created_for(self):
        self.root_company.account_config_id.account_return_periodicity = "trimester"
        branch = self.setup_other_company(
            name="Monthly branch", parent_id=self.root_company.id
        )["company"]
        branch.account_config_id.account_return_periodicity = "monthly"

        wizard = self.env["wizard.account.return.create"].create(
            {
                "company_id": branch.id,
                "date_from": "2023-10-01",
                "date_to": "2023-10-31",
                "return_type_id": self.return_type.id,
            }
        )
        self.assertTrue(wizard.show_warning_wrong_dates)

        wizard._onchange_return_type_id()
        self.assertEqual(
            (wizard.date_from, wizard.date_to), (date(2023, 10, 1), date(2023, 12, 31))
        )
        self.assertFalse(wizard.show_warning_wrong_dates)

    def test_branch_fiscal_year_periodicity_reads_the_root_fiscal_years(self):
        self.env["account.fiscal.year"].create(
            {
                "name": "Long fiscal year",
                "date_from": "2023-07-01",
                "date_to": "2024-12-31",
                "company_id": self.root_company.id,
            }
        )
        branch = self.setup_other_company(
            name="Fiscal year branch", parent_id=self.root_company.id
        )["company"]
        self.return_type.with_company(branch).deadline_periodicity = "fiscalyear"
        self.assertEqual(self.return_type._get_periodicity_months_delay(branch), 18)

    def _setup_branch(self, name, parent, vat=False):
        with self._patch_returns_generation():
            return self.setup_other_company(name=name, parent_id=parent.id, vat=vat)[
                "company"
            ]

    def _assert_vat_filing(self, filing_by_company):
        wizard_vals = {
            "date_from": "2024-01-01",
            "date_to": "2024-01-31",
            "return_type_id": self.return_type.id,
        }
        for company, filing_company in filing_by_company.items():
            with self.subTest(company=company.name):
                self.assertEqual(company._get_vat_filing_company(), filing_company)
                self.assertEqual(
                    self.return_type._can_return_exist(company),
                    company == filing_company,
                )
                wizard = self.env["wizard.account.return.create"].create(
                    {**wizard_vals, "company_id": company.id}
                )
                self.assertEqual(
                    wizard._get_return_company_and_tax_unit()[0], filing_company
                )

    def test_same_vat_sub_branch_resolves_to_the_root_that_files_for_it(self):
        branch = self._setup_branch("Branch without VAT", self.root_company)
        sub_branch = self._setup_branch(
            "Sub-branch with the root's VAT", branch, vat=self.root_company.vat
        )
        self._assert_vat_filing(
            {
                self.root_company: self.root_company,
                branch: self.root_company,
                sub_branch: self.root_company,
            }
        )

    def test_vat_filing_stops_at_a_branch_with_another_vat(self):
        other_vat_branch = self._setup_branch(
            "Branch with its own VAT", self.root_company, vat="US98765432"
        )
        vatless_sub_branch = self._setup_branch(
            "Sub-branch without VAT", other_vat_branch
        )
        root_vat_sub_sub_branch = self._setup_branch(
            "Sub-sub-branch with the root's VAT",
            vatless_sub_branch,
            vat=self.root_company.vat,
        )
        self._assert_vat_filing(
            {
                self.root_company: self.root_company,
                other_vat_branch: other_vat_branch,
                vatless_sub_branch: other_vat_branch,
                root_vat_sub_sub_branch: root_vat_sub_sub_branch,
            }
        )

    def _create_conditional_return_type(self):
        report = self.env["report.formula"].create(
            {
                "root_report_id": self.env.ref("account.generic_ec_sales_report").id,
                "name": "Marin Conditional EC Sales Report",
            }
        )
        return_type = self.env["account.return.type"].create(
            {
                "name": "EC Sales List (Marin)",
                "report_id": report.id,
                "auto_generate": False,
                "default_deadline_start_date": "2024-01-01",
                "default_deadline_periodicity": "monthly",
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "__test__",
                "name": "marin_conditional_return_type",
                "model": "account.return.type",
                "res_id": return_type.id,
            }
        )
        return return_type

    def _create_tagged_entry(self, journal, tag, entry_date, post=True):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": entry_date,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "credit": 100.0,
                            "tax_tag_ids": [Command.set(tag.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_assets"
                            ].id,
                            "debit": 100.0,
                        }
                    ),
                ],
            }
        )
        if post:
            move.action_post()
        return move

    def test_conditional_return_needs_posted_activity_in_the_filing_scope(self):
        return_type = self._create_conditional_return_type()
        tag = self.env["account.account.tag"].create(
            {"name": "Marin EC goods", "applicability": "taxes"}
        )
        branch = self._setup_branch("Branch without VAT", self.root_company)
        branch_journal = self.env["account.journal"].create(
            {
                "name": "Branch Miscellaneous",
                "code": "BMSC",
                "type": "general",
                "company_id": branch.id,
            }
        )

        def generate():
            self.env["account.return.type"]._generate_conditional_return(
                "__test__.marin_conditional_return_type",
                self.root_company,
                None,
                need_domain=[("tax_tag_ids", "in", tag.ids)],
            )
            return self.env["account.return"].search([("type_id", "=", return_type.id)])

        self._create_tagged_entry(
            self.company_data["default_journal_misc"], tag, "2023-12-10", post=False
        )
        self._create_tagged_entry(branch_journal, tag, "2024-01-05")
        self.assertFalse(generate())

        self._create_tagged_entry(branch_journal, tag, "2023-12-20")
        returns = generate()
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns.company_id, self.root_company)
        self.assertEqual(
            (returns.date_from, returns.date_to),
            (date(2023, 12, 1), date(2023, 12, 31)),
        )
        self.assertIn(branch, returns.company_ids)

    def test_conditional_return_probes_each_requested_period(self):
        return_type = self._create_conditional_return_type()
        tag = self.env["account.account.tag"].create(
            {"name": "Marin EC services", "applicability": "taxes"}
        )
        self._create_tagged_entry(
            self.company_data["default_journal_misc"], tag, "2023-11-15"
        )
        self.env["account.return.type"]._generate_conditional_return(
            "__test__.marin_conditional_return_type",
            self.root_company,
            None,
            need_domain=[("tax_tag_ids", "in", tag.ids)],
            periods_back=range(-1, 4),
        )
        returns = self.env["account.return"].search([("type_id", "=", return_type.id)])
        self.assertEqual(
            [(r.date_from, r.date_to) for r in returns],
            [(date(2023, 11, 1), date(2023, 11, 30))],
        )

    def test_conditional_return_without_need_domain_always_covers_the_previous_period(
        self,
    ):
        return_type = self._create_conditional_return_type()
        self.env["account.return.type"]._generate_conditional_return(
            "__test__.marin_conditional_return_type", self.root_company, None
        )
        self.env["account.return.type"]._generate_conditional_return(
            "__test__.marin_missing_return_type", self.root_company, None
        )
        returns = self.env["account.return"].search([("type_id", "=", return_type.id)])
        self.assertEqual(
            [(r.date_from, r.date_to) for r in returns],
            [(date(2023, 12, 1), date(2023, 12, 31))],
        )

    def test_a_country_deadline_never_overrides_the_configured_delay(self):
        def country_deadline(
            account_return, company, return_type, xmlid, date_from, date_to
        ):
            return date(2099, 1, 1)

        self.root_company.account_config_id.account_return_periodicity = "monthly"
        with patch.object(
            self.registry["account.return"], "_evaluate_deadline", country_deadline
        ):
            self.assertEqual(
                self.env["account.return"]._get_deadline(
                    self.root_company,
                    self.return_type,
                    "__test__.marin_conditional_return_type",
                    date(2024, 1, 1),
                    date(2024, 1, 31),
                ),
                date(2099, 1, 1),
            )
            self.return_type.with_company(self.root_company).deadline_days_delay = 12
            self.assertEqual(
                self.env["account.return"]._get_deadline(
                    self.root_company,
                    self.return_type,
                    "__test__.marin_conditional_return_type",
                    date(2024, 1, 1),
                    date(2024, 1, 31),
                ),
                date(2024, 2, 12),
            )

    def _create_foreign_vat_branch(self, country):
        branch = self._setup_branch("Foreign VAT branch", self.root_company)
        self.env["account.fiscal.position"].create(
            {
                "name": "Foreign VAT",
                "company_id": branch.id,
                "country_id": country.id,
                "foreign_vat": "BE0477472701",
            }
        )
        return branch

    def test_a_type_country_over_a_countryless_report_is_foreign_for_a_branch(self):
        belgium = self.env.ref("base.be")
        return_type = self._create_conditional_return_type()
        return_type.country_id = belgium
        branch = self._create_foreign_vat_branch(belgium)
        with self._patch_returns_generation():
            (
                self.root_company + branch
            ).account_config_id.account_opening_date = "2023-01-01"
            self.env["account.return.type"]._generate_conditional_return(
                "__test__.marin_conditional_return_type", branch, None
            )
            branch_returns = self.env["account.return"].search(
                [("type_id", "=", return_type.id), ("company_id", "=", branch.id)]
            )
            self.assertTrue(return_type._can_return_exist(branch))
            self.assertEqual(len(branch_returns), 1)

            self.env["account.return"].with_context(
                allowed_company_ids=(branch + self.root_company).ids
            ).action_refresh_all_returns()
        self.assertTrue(branch_returns.exists())

    def test_conditional_return_is_not_created_for_a_tax_unit_member(self):
        return_type = self._create_conditional_return_type()
        member = self.setup_other_company(name="Tax unit member", vat="US98765432")[
            "company"
        ]
        tax_unit = self.env["account.tax.unit"].create(
            {
                "name": "Marin tax unit",
                "country_id": self.root_company.tax_config_id.account_fiscal_country_id.id,
                "vat": "US11111111",
                "company_ids": [Command.set((self.root_company + member).ids)],
                "main_company_id": self.root_company.id,
            }
        )
        created = []
        create = self.registry["account.return"].create

        def record_create(account_return, vals_list):
            records = create(account_return, vals_list)
            created.extend(records.mapped("company_id"))
            return records

        with patch.object(self.registry["account.return"], "create", record_create):
            for company in (member, self.root_company):
                self.env["account.return.type"]._generate_conditional_return(
                    "__test__.marin_conditional_return_type", company, tax_unit
                )
        self.assertEqual(created, [self.root_company])
        returns = self.env["account.return"].search([("type_id", "=", return_type.id)])
        self.assertEqual(returns.tax_unit_id, tax_unit)

    def test_deadlines_are_not_evaluated_for_periods_due_before_the_opening(self):
        self.root_company.account_config_id.account_return_periodicity = "monthly"
        evaluated = []

        def deadline_with_rules_from_2022(
            account_return, company, return_type, xmlid, date_from, date_to
        ):
            if return_type == self.return_type:
                evaluated.append(date_to)
            if date_to < date(2022, 1, 1):
                raise UserError("no version in force")
            return date_to + timedelta(days=17)

        with (
            self._patch_returns_generation(),
            patch.object(
                self.registry["account.return"],
                "_evaluate_deadline",
                deadline_with_rules_from_2022,
            ),
        ):
            self.root_company.account_config_id.account_opening_date = "2023-06-01"
        returns = self.env["account.return"].search(
            [("type_id", "=", self.return_type.id)], order="date_from"
        )
        self.assertEqual(returns[0].date_from, date(2023, 5, 1))
        self.assertEqual(returns[-1].date_to, date(2024, 11, 30))
        self.assertEqual(min(evaluated), date(2023, 4, 30))

    def _create_foreign_ec_sales_list_return(self):
        belgium = self.env.ref("base.be")
        return_type = self._create_conditional_return_type()
        return_type.country_id = belgium
        branch = self._create_foreign_vat_branch(belgium)
        with self._patch_returns_generation():
            (
                self.root_company + branch
            ).account_config_id.account_opening_date = "2023-01-01"
            self.env["account.return.type"]._generate_conditional_return(
                "__test__.marin_conditional_return_type", branch, None
            )
        return self.env["account.return"].search(
            [("type_id", "=", return_type.id), ("company_id", "=", branch.id)]
        )

    def test_a_foreign_return_named_after_its_type_country(self):
        account_return = self._create_foreign_ec_sales_list_return()
        self.assertEqual(len(account_return), 1)
        self.assertTrue(account_return.name.endswith("(BE)"), account_return.name)

    def _create_foreign_tax_return(self, branch):
        belgium = self.env.ref("base.be")
        return_type = self.env["account.return.type"].create(
            {
                "name": "VAT Return (Marin, BE)",
                "report_id": self.tax_report.id,
                "country_id": belgium.id,
                "auto_generate": False,
            }
        )
        return self.env["account.return"].create(
            {
                "name": "BE VAT January",
                "type_id": return_type.id,
                "company_id": branch.id,
                "date_from": "2024-01-01",
                "date_to": "2024-01-31",
            }
        )

    def _check_results(self, account_return):
        return {check.code: check.result for check in account_return.check_ids}

    def test_returns_of_a_type_country_in_europe_run_the_vies_check(self):
        self.ensure_installed("account_vat")
        ec_sales_list_return = self._create_foreign_ec_sales_list_return()
        tax_return = self._create_foreign_tax_return(ec_sales_list_return.company_id)
        (
            tax_return + ec_sales_list_return
        ).company_id.account_config_id.vat_check_vies = True
        with patch(
            "odoo.addons.account_vat.models.res_partner.ResPartner._check_vies",
            lambda partner, vat: {"valid": True},
        ):
            (tax_return + ec_sales_list_return).refresh_checks()
        for account_return in (tax_return, ec_sales_list_return):
            with self.subTest(account_return=account_return.type_id.name):
                self.assertEqual(
                    self._check_results(account_return).get("check_partner_vies"),
                    "reviewed",
                )

    def test_tax_closing_reads_the_tax_groups_of_the_type_country(self):
        tax_return = self._create_foreign_tax_return(
            self._create_foreign_vat_branch(self.env.ref("base.be"))
        )
        payable, receivable = (
            self.company_data["default_account_tax_sale"].copy({"code": code})
            for code in ("252001", "152001")
        )
        tax_group = self.env["account.tax.group"].create(
            {
                "name": "BE VAT",
                "country_id": tax_return.type_id.country_id.id,
                "company_ids": [Command.set(self.root_company.ids)],
                "tax_payable_account_id": payable.id,
                "tax_receivable_account_id": receivable.id,
            }
        )
        self.env["account.tax"].create(
            {
                "name": "BE 21%",
                "amount": 21,
                "country_id": tax_return.type_id.country_id.id,
                "company_ids": [Command.set(self.root_company.ids)],
                "tax_group_id": tax_group.id,
            }
        )
        self.assertEqual(
            tax_return._get_tax_group_closing_accounts(), (payable, receivable)
        )

    def test_a_domestic_type_country_over_a_countryless_report_locks_tax(self):
        self.return_type.country_id = (
            self.root_company.tax_config_id.account_fiscal_country_id
        )
        tax_return = self.env["account.return"].create(
            {
                "name": "Domestic VAT January",
                "type_id": self.return_type.id,
                "company_id": self.root_company.id,
                "date_from": "2024-01-01",
                "date_to": "2024-01-31",
            }
        )
        tax_return.action_validate(bypass_failing_tests=True)
        self.assertEqual(
            self.root_company.account_config_id.tax_lock_date, date(2024, 1, 31)
        )

    def _post_a_domestic_and_a_belgian_sale(self):
        belgium = self.env.ref("base.be")
        self.root_company.account_config_id.account_return_periodicity = "monthly"
        self.root_company.account_config_id.account_opening_date = "2023-01-01"
        foreign_vat = self.env["account.fiscal.position"].create(
            {
                "name": "Belgian VAT",
                "company_id": self.root_company.id,
                "country_id": belgium.id,
                "foreign_vat": "BE0477472701",
            }
        )
        payable, receivable = (
            self.company_data["default_account_tax_sale"].copy({"code": code})
            for code in ("252002", "152002")
        )
        domestic_tax = self.company_data["default_tax_sale"]
        belgian_tax = domestic_tax.copy(
            {
                "name": "BE 21%",
                "amount": 21,
                "country_id": belgium.id,
                "tax_group_id": self.env["account.tax.group"]
                .create(
                    {
                        "name": "BE VAT",
                        "country_id": belgium.id,
                        "company_ids": [Command.set(self.root_company.ids)],
                        "tax_payable_account_id": payable.id,
                        "tax_receivable_account_id": receivable.id,
                    }
                )
                .id,
            }
        )
        self.env["account.move"].create(
            [
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": invoice_date,
                    "fiscal_position_id": fiscal_position.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "line",
                                "price_unit": amount,
                                "tax_ids": [Command.set(tax.ids)],
                            }
                        )
                    ],
                }
                for invoice_date, fiscal_position, tax, amount in (
                    (
                        "2024-01-10",
                        self.env["account.fiscal.position"],
                        domestic_tax,
                        100.0,
                    ),
                    ("2024-01-12", foreign_vat, belgian_tax, 1000.0),
                )
            ]
        ).action_post()
        return domestic_tax, belgian_tax, payable | receivable

    def test_a_foreign_type_over_a_countryless_report_closes_its_country_only(self):
        belgium = self.env.ref("base.be")
        _domestic_tax, _belgian_tax, belgian_accounts = (
            self._post_a_domestic_and_a_belgian_sale()
        )
        return_type = self.env["account.return.type"].create(
            {
                "name": "VAT Return (Marin, BE)",
                "report_id": self.tax_report.id,
                "country_id": belgium.id,
                "auto_generate": False,
            }
        )
        tax_return = self.env["account.return"].create(
            {
                "name": "BE VAT January",
                "type_id": return_type.id,
                "company_id": self.root_company.id,
                "date_from": "2024-01-01",
                "date_to": "2024-01-31",
            }
        )

        tax_return.action_validate(bypass_failing_tests=True)

        closed_taxes = tax_return.closing_move_ids.line_ids.filtered(
            lambda line: line.account_id not in belgian_accounts
        )
        self.assertRecordValues(
            closed_taxes,
            [{"name": "BE 21%", "debit": 210.0, "credit": 0.0}],
        )
        self.assertEqual(tax_return.period_amount_to_pay, 210.0)

    def _january_returns_of_the_countryless_type(self):
        self.env["account.return.type"]._sync_all_returns(self.root_company)
        self.env["account.return"].search(
            [
                ("type_id", "=", self.return_type.id),
                ("company_id", "=", self.root_company.id),
                ("date_to", "<", "2024-01-01"),
            ]
        )._as_workflow_step().write({"is_completed": True})
        return self.env["account.return"].search(
            [
                ("type_id", "=", self.return_type.id),
                ("company_id", "=", self.root_company.id),
                ("date_from", "=", "2024-01-01"),
            ]
        )

    def _closed_tax_amounts(self, tax_returns, taxes):
        return sorted(
            (line.name, line.debit)
            for line in tax_returns.closing_move_ids.line_ids
            if line.name in taxes.mapped("name")
        )

    def test_a_countryless_domestic_return_leaves_foreign_vat_lines_out(self):
        domestic_tax, belgian_tax, _belgian_accounts = (
            self._post_a_domestic_and_a_belgian_sale()
        )
        domestic_return = self._january_returns_of_the_countryless_type().filtered(
            lambda r: not r.name.endswith("(BE)")
        )

        domestic_return.action_validate(bypass_failing_tests=True)

        self.assertEqual(
            self._closed_tax_amounts(domestic_return, domestic_tax + belgian_tax),
            [(domestic_tax.name, 15.0)],
        )

    def test_a_countryless_type_is_filed_for_each_foreign_vat_country(self):
        domestic_tax, belgian_tax, _belgian_accounts = (
            self._post_a_domestic_and_a_belgian_sale()
        )
        returns = self._january_returns_of_the_countryless_type()
        self.assertEqual(len(returns), 2)
        fiscal_country = self.root_company.tax_config_id.account_fiscal_country_id
        domestic_return = returns.filtered(lambda r: r.country_id == fiscal_country)
        foreign_return = returns - domestic_return
        self.assertEqual(foreign_return.country_id, self.env.ref("base.be"))
        self.assertTrue(foreign_return.name.endswith("(BE)"), foreign_return.name)

        with self.subTest("a second sync creates nothing"):
            self.assertEqual(self._january_returns_of_the_countryless_type(), returns)

        foreign_return.action_validate(bypass_failing_tests=True)
        domestic_return.action_validate(bypass_failing_tests=True)

        self.assertEqual(
            self._closed_tax_amounts(foreign_return, domestic_tax + belgian_tax),
            [("BE 21%", 210.0)],
        )
        self.assertEqual(
            self._closed_tax_amounts(returns, domestic_tax + belgian_tax),
            sorted([(domestic_tax.name, 15.0), ("BE 21%", 210.0)]),
        )

    def test_the_creation_wizard_files_a_countryless_type_for_a_foreign_country(self):
        belgium = self.env.ref("base.be")
        self._post_a_domestic_and_a_belgian_sale()
        self.env["account.return"].search(
            [("type_id", "=", self.return_type.id)]
        ).sudo().unlink()
        wizard = self.env["wizard.account.return.create"].create(
            {
                "return_type_id": self.return_type.id,
                "country_id": belgium.id,
                "date_from": "2024-01-01",
                "date_to": "2024-01-31",
            }
        )
        self.assertEqual(
            wizard.available_country_ids,
            self.root_company.tax_config_id.account_fiscal_country_id + belgium,
        )
        self.assertTrue(wizard.show_country_id)
        wizard.action_create_manual_account_returns()

        created = self.env["account.return"].search(
            [("type_id", "=", self.return_type.id)]
        )
        self.assertEqual(created.country_id, belgium)
        self.assertEqual(created.date_to, date(2024, 1, 31))

    def _create_belgian_tax_type(self, auto_generate):
        return self.env["account.return.type"].create(
            {
                "name": "VAT Return (Marin, BE)",
                "report_id": self.tax_report.id,
                "country_id": self.env.ref("base.be").id,
                "default_deadline_start_date": "2024-01-01",
                "auto_generate": auto_generate,
            }
        )

    def _january_returns(self, return_type, company=None):
        return self.env["account.return"].search(
            [
                ("type_id", "=", return_type.id),
                ("company_id", "=", (company or self.root_company).id),
                ("date_from", "=", "2024-01-01"),
            ]
        )

    def test_a_country_tax_type_files_its_country_instead_of_the_countryless_type(
        self,
    ):
        domestic_tax, belgian_tax, _belgian_accounts = (
            self._post_a_domestic_and_a_belgian_sale()
        )
        belgian_type = self._create_belgian_tax_type(auto_generate=True)
        countryless_returns = self._january_returns_of_the_countryless_type()
        self.assertEqual(
            countryless_returns.country_id,
            self.root_company.tax_config_id.account_fiscal_country_id,
        )
        belgian_return = self._january_returns(belgian_type)
        self.assertEqual(len(belgian_return), 1)
        self.env["account.return"].search(
            [("type_id", "=", belgian_type.id), ("date_to", "<", "2024-01-01")]
        )._as_workflow_step().write({"is_completed": True})

        for tax_return in countryless_returns + belgian_return:
            tax_return.action_validate(bypass_failing_tests=True)

        self.assertEqual(
            self._closed_tax_amounts(
                countryless_returns + belgian_return, domestic_tax + belgian_tax
            ),
            sorted([(domestic_tax.name, 15.0), ("BE 21%", 210.0)]),
        )

    def test_a_country_tax_type_filed_by_hand_also_replaces_the_countryless_type(
        self,
    ):
        self._post_a_domestic_and_a_belgian_sale()
        self._january_returns_of_the_countryless_type()
        self._create_belgian_tax_type(auto_generate=False)

        countryless_returns = self._january_returns_of_the_countryless_type()

        self.assertEqual(
            countryless_returns.country_id,
            self.root_company.tax_config_id.account_fiscal_country_id,
        )

    def test_a_countryless_type_is_not_filed_where_the_fiscal_country_has_a_type(
        self,
    ):
        self._post_a_domestic_and_a_belgian_sale()
        self.assertTrue(self._january_returns(self.return_type))
        self.env["account.return.type"].create(
            {
                "name": "VAT Return (Marin, domestic)",
                "report_id": self.tax_report.id,
                "country_id": self.root_company.tax_config_id.account_fiscal_country_id.id,
                "auto_generate": False,
            }
        )

        self.assertEqual(
            self._january_returns_of_the_countryless_type().country_id,
            self.env.ref("base.be"),
        )

    def test_a_fiscal_country_change_carries_the_unposted_countryless_returns(self):
        self.root_company.account_config_id.account_return_periodicity = "monthly"
        self.root_company.account_config_id.account_opening_date = "2023-01-01"
        former_country = self.root_company.tax_config_id.account_fiscal_country_id
        self._january_returns_of_the_countryless_type()
        returns = self.env["account.return"].search(
            [("type_id", "=", self.return_type.id)]
        )
        posted = returns.filtered("is_completed")
        self.assertTrue(posted)
        self.assertTrue(returns - posted)

        canada = self.env.ref("base.ca")
        self.root_company.tax_config_id.account_fiscal_country_id = canada
        self.env["account.return.type"]._sync_all_returns(self.root_company)

        self.assertEqual(
            self.env["account.return"].search([("type_id", "=", self.return_type.id)]),
            returns,
        )
        self.assertEqual(posted.country_id, former_country)
        self.assertEqual((returns - posted).country_id, canada)

    def test_a_move_to_a_foreign_vat_country_keeps_one_return_per_period(self):
        belgium = self.env.ref("base.be")
        self._post_a_domestic_and_a_belgian_sale()
        self._january_returns_of_the_countryless_type()
        returns = self.env["account.return"].search(
            [("type_id", "=", self.return_type.id)]
        )
        belgian_returns = returns.filtered(
            lambda account_return: account_return.country_id == belgium
        )
        posted = returns.filtered("is_completed")
        self.assertTrue(returns - belgian_returns - posted)

        self.env["account.fiscal.position"].search(
            [("company_id", "=", self.root_company.id), ("country_id", "=", belgium.id)]
        ).active = False
        self.root_company.tax_config_id.account_fiscal_country_id = belgium
        self.env["account.return.type"]._sync_all_returns(self.root_company)

        self.assertEqual(
            self.env["account.return"].search([("type_id", "=", self.return_type.id)]),
            belgian_returns | posted,
        )

    def test_the_eu_check_suite_runs_on_tax_returns_only(self):
        self.root_company.tax_config_id.account_fiscal_country_id = self.env.ref(
            "base.be"
        )
        annual_closing, tax_return = self.env["account.return"].create(
            [
                {
                    "name": f"{return_type.name} 2023",
                    "type_id": return_type.id,
                    "company_id": self.root_company.id,
                    "date_from": "2023-01-01",
                    "date_to": "2023-12-31",
                }
                for return_type in (
                    self.env.ref("account.annual_corporate_tax_return_type"),
                    self.return_type,
                )
            ]
        )
        suite_runs = []
        run_eu_suite = self.registry["account.return"]._check_suite_eu_vat_report

        def record_eu_suite(account_return, check_codes_to_ignore):
            suite_runs.append(account_return)
            return run_eu_suite(account_return, check_codes_to_ignore)

        with patch.object(
            self.registry["account.return"],
            "_check_suite_eu_vat_report",
            record_eu_suite,
        ):
            (annual_closing + tax_return).refresh_checks()

        self.assertEqual(annual_closing.country_id, tax_return.country_id)
        self.assertEqual(suite_runs, [tax_return])

    def test_a_same_vat_branch_files_no_foreign_return_its_root_covers(self):
        belgium = self.env.ref("base.be")
        self._post_a_domestic_and_a_belgian_sale()
        branch = self._create_foreign_vat_branch(belgium)
        branch.account_config_id.account_opening_date = "2023-01-01"

        self.env["account.return.type"]._sync_all_returns(self.root_company)

        root_belgian_returns = self._january_returns(self.return_type).filtered(
            lambda account_return: account_return.country_id == belgium
        )
        self.assertEqual(len(root_belgian_returns), 1)
        self.assertIn(branch, root_belgian_returns.company_ids)
        self.assertFalse(
            self.env["account.return"].search(
                [("company_id", "=", branch.id), ("country_id", "=", belgium.id)]
            )
        )

    def test_a_same_vat_branch_with_another_foreign_vat_files_its_own_return(self):
        belgium = self.env.ref("base.be")
        branch = self._setup_branch("Branch with its own BE VAT", self.root_company)
        self.env["account.fiscal.position"].create(
            {
                "name": "Branch Belgian VAT",
                "company_id": branch.id,
                "country_id": belgium.id,
                "foreign_vat": "BE0897223670",
            }
        )
        self._post_a_domestic_and_a_belgian_sale()
        branch.account_config_id.account_opening_date = "2023-01-01"

        self.env["account.return.type"]._sync_all_returns(self.root_company)

        self.assertEqual(
            len(
                self._january_returns(self.return_type, branch).filtered(
                    lambda account_return: account_return.country_id == belgium
                )
            ),
            1,
        )

    def test_the_creation_wizard_offers_no_country_a_country_type_replaces(self):
        belgium = self.env.ref("base.be")
        fiscal_country = self.root_company.tax_config_id.account_fiscal_country_id
        self._post_a_domestic_and_a_belgian_sale()
        self._create_belgian_tax_type(auto_generate=True)
        wizard_vals = {
            "return_type_id": self.return_type.id,
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
        }

        wizard = self.env["wizard.account.return.create"].create(wizard_vals)
        self.assertIn(self.return_type, wizard.available_return_type_ids)
        self.assertEqual(wizard.available_country_ids, fiscal_country)
        self.assertEqual(wizard.country_id, fiscal_country)

        wizard.country_id = belgium
        with self.assertRaisesRegex(UserError, "VAT Return \\(Marin, BE\\)"):
            wizard.action_create_manual_account_returns()

        self.env["account.return.type"].create(
            {
                "name": "VAT Return (Marin, domestic)",
                "report_id": self.tax_report.id,
                "country_id": fiscal_country.id,
                "auto_generate": False,
            }
        )
        wizard = self.env["wizard.account.return.create"].create(wizard_vals)
        self.assertNotIn(self.return_type, wizard.available_return_type_ids)
        wizard.return_type_id = self.return_type
        wizard.country_id = fiscal_country
        with self.assertRaisesRegex(UserError, "VAT Return \\(Marin, domestic\\)"):
            wizard.action_create_manual_account_returns()

    def _create_foreign_tax_unit(self):
        self.tax_report.filter_multi_company = "tax_units"
        self.root_company.account_config_id.account_return_periodicity = "monthly"
        self.root_company.account_config_id.account_opening_date = "2023-01-01"
        member = self.setup_other_company(name="French unit member", vat="US98765432")[
            "company"
        ]
        return self.env["account.tax.unit"].create(
            {
                "name": "French tax unit",
                "country_id": self.env.ref("base.fr").id,
                "vat": "FR23334175221",
                "company_ids": [Command.set((self.root_company + member).ids)],
                "main_company_id": self.root_company.id,
            }
        )

    def _returns_of_the_countryless_type(self, **domain):
        return self.env["account.return"].search(
            [
                ("type_id", "=", self.return_type.id),
                *((field, "=", value) for field, value in domain.items()),
            ]
        )

    def test_a_foreign_tax_unit_keeps_its_returns_across_syncs(self):
        tax_unit = self._create_foreign_tax_unit()
        self.env["account.return.type"]._sync_all_returns(self.root_company)
        unit_returns = self._returns_of_the_countryless_type(tax_unit_id=tax_unit.id)
        self.assertTrue(unit_returns)
        self.assertEqual(unit_returns.country_id, tax_unit.country_id)

        self.env["account.return.type"]._sync_all_returns(self.root_company)

        self.assertEqual(
            self._returns_of_the_countryless_type(tax_unit_id=tax_unit.id),
            unit_returns,
        )

    def test_a_posted_foreign_tax_unit_return_does_not_cover_a_domestic_period(self):
        tax_unit = self._create_foreign_tax_unit()
        fiscal_country = self.root_company.tax_config_id.account_fiscal_country_id
        self.env["account.return.type"]._sync_all_returns(self.root_company)
        self._returns_of_the_countryless_type(
            tax_unit_id=tax_unit.id
        )._as_workflow_step().write({"is_completed": True})
        removed_returns = self._returns_of_the_countryless_type(
            country_id=fiscal_country.id
        ).filtered(
            lambda account_return: (
                date(2023, 6, 1) <= account_return.date_from <= date(2023, 7, 31)
            )
        )
        removed_periods = {
            (account_return.date_from, account_return.date_to)
            for account_return in removed_returns
        }
        self.assertEqual(len(removed_periods), 2)
        removed_returns.sudo().unlink()

        self.env["account.return.type"]._sync_all_returns(self.root_company)

        domestic_periods = {
            (account_return.date_from, account_return.date_to)
            for account_return in self._returns_of_the_countryless_type(
                country_id=fiscal_country.id
            )
        }
        self.assertEqual(removed_periods - domestic_periods, set())

    def _belgian_returns_holding_work(self):
        belgium = self.env.ref("base.be")
        self._post_a_domestic_and_a_belgian_sale()
        self._january_returns_of_the_countryless_type()
        belgian_returns = self._returns_of_the_countryless_type(
            country_id=belgium.id
        ).sorted("date_from")
        idle, attached, discussed, planned, reviewed = belgian_returns[-5:]
        self.env["ir.attachment"].create(
            {
                "name": "statement.pdf",
                "raw": b"%PDF-1.4",
                "res_model": attached._name,
                "res_id": attached.id,
            }
        )
        discussed.message_post(body="Waiting for the bank", message_type="comment")
        planned.activity_schedule(
            act_type_xmlid="mail.mail_activity_data_todo",
            summary="Ask for the Belgian statement",
        )
        check = self.env["account.return.check"].create(
            {
                "code": "marin_manual_check",
                "name": "Belgian ledger agreed",
                "return_id": reviewed.id,
            }
        )
        check.result = "reviewed"
        return idle, attached + discussed + planned + reviewed

    def test_a_replaced_return_holding_work_is_kept_and_handed_to_the_user(self):
        idle, holding_work = self._belgian_returns_holding_work()
        belgian_type = self._create_belgian_tax_type(auto_generate=False)

        self.env["account.return.type"]._sync_all_returns(self.root_company)

        self.assertFalse(idle.exists())
        self.assertEqual(holding_work.exists(), holding_work)
        self.assertEqual(holding_work.mapped("manually_created"), [True] * 4)
        for account_return in holding_work:
            with self.subTest(account_return=account_return.name):
                self.assertIn(belgian_type.name, account_return.message_ids[:1].body)

        with self.subTest("a later sync notes nothing more"):
            messages = holding_work.message_ids
            self.env["account.return.type"]._sync_all_returns(self.root_company)
            self.assertEqual(holding_work.message_ids, messages)

    def test_the_returns_holding_user_work_are_told_apart(self):
        idle, holding_work = self._belgian_returns_holding_work()
        self.assertEqual(
            (idle + holding_work)._get_returns_holding_user_work(), holding_work
        )

    def test_a_second_sync_reads_each_type_country_once(self):
        self._post_a_domestic_and_a_belgian_sale()
        self._january_returns_of_the_countryless_type()
        self.assertGreater(
            self.env["account.return"].search_count(
                [("type_id", "=", self.return_type.id), ("is_completed", "=", False)]
            ),
            20,
        )
        self.env.invalidate_all()
        with self.assertQueryCount(78):
            self.env["account.return.type"]._sync_all_returns(self.root_company)

    def test_a_return_holding_work_outlives_a_later_opening_date(self):
        self.root_company.account_config_id.account_return_periodicity = "monthly"
        self.root_company.account_config_id.account_opening_date = "2023-01-01"
        early_idle, early_discussed = self._returns_of_the_countryless_type().sorted(
            "date_from"
        )[:2]
        early_discussed.message_post(body="Asked the bank", message_type="comment")

        self.root_company.account_config_id.account_opening_date = "2023-09-01"
        self.env["account.return.type"]._sync_all_returns(self.root_company)

        self.assertFalse(early_idle.exists())
        self.assertTrue(early_discussed.exists())
        self.assertTrue(early_discussed.manually_created)
        self.assertIn(
            "no longer generated for its company", early_discussed.message_ids[:1].body
        )

    def test_the_vacuum_keeps_a_return_holding_work(self):
        self.root_company.account_config_id.account_opening_date = "2023-01-01"
        idle, discussed = self.env["account.return"].create(
            [
                {
                    "name": f"VAT {date_from}",
                    "type_id": self.return_type.id,
                    "company_id": self.root_company.id,
                    "date_from": date_from,
                    "date_to": date_to,
                }
                for date_from, date_to in (
                    ("2022-05-01", "2022-05-31"),
                    ("2022-06-01", "2022-06-30"),
                )
            ]
        )
        discussed.message_post(body="Asked the bank", message_type="comment")

        self.env["account.return.type"]._sync_all_returns(self.root_company)

        self.assertFalse(idle.exists())
        self.assertTrue(discussed.exists())
        self.assertTrue(discussed.manually_created)
        self.assertIn(
            "no longer generated for its company", discussed.message_ids[:1].body
        )
