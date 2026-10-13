import calendar
from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time

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
            cls.return_type._try_create_returns_for_fiscal_year(main_company, tax_unit)

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
