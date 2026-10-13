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
