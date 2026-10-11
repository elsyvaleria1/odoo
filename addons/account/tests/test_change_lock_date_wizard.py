from contextlib import closing
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import frozendict

from odoo.addons.account.models.account_config import SOFT_LOCK_DATE_FIELDS
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestChangeLockDateWizard(AccountTestInvoicingCommon):
    def test_exception_generation(self):
        self.env["account.lock_exception"].search([]).sudo().unlink()

        for lock_date_field in SOFT_LOCK_DATE_FIELDS:
            with (
                self.subTest(lock_date_field=lock_date_field),
                closing(self.cr.savepoint()),
            ):
                self.env["wizard.account.config.update.lock.date"].create(
                    {lock_date_field: "2010-01-01"}
                ).change_lock_date()
                self.assertEqual(
                    self.env.company.account_config_id[lock_date_field],
                    fields.Date.from_string("2010-01-01"),
                )

                self.env["wizard.account.config.update.lock.date"].create(
                    {lock_date_field: "2011-01-01"}
                ).change_lock_date()
                self.assertEqual(
                    self.env.company.account_config_id[lock_date_field],
                    fields.Date.from_string("2011-01-01"),
                )

                wizard = self.env["wizard.account.config.update.lock.date"].create(
                    {
                        lock_date_field: False,
                        "exception_applies_to": "everyone",
                        "exception_duration": "1h",
                        "exception_reason": ":TestChangeLockDateWizard.test_exception_generation; remove",
                    }
                )
                wizard.change_lock_date()
                self.assertEqual(self.env["account.lock_exception"].search_count([]), 1)
                exception = self.env["account.lock_exception"].search([])
                self.assertEqual(len(exception), 1)
                self.assertRecordValues(
                    exception,
                    [
                        {
                            lock_date_field: False,
                            "company_id": self.env.company.id,
                            "user_id": False,
                            "create_uid": self.env.user.id,
                            "end_datetime": self.env.cr.now() + timedelta(hours=1),
                            "reason": ":TestChangeLockDateWizard.test_exception_generation; remove",
                        }
                    ],
                )
                exception.sudo().unlink()

                self.assertEqual(self.env["account.lock_exception"].search_count([]), 0)

                self.env["wizard.account.config.update.lock.date"].create(
                    {lock_date_field: "2009-01-01"}
                ).change_lock_date()
                self.assertEqual(
                    self.env.company.account_config_id[lock_date_field],
                    fields.Date.from_string("2011-01-01"),
                )
                exception = self.env["account.lock_exception"].search([])
                self.assertEqual(len(exception), 1)
                self.assertRecordValues(
                    exception,
                    [
                        {
                            lock_date_field: fields.Date.from_string("2009-01-01"),
                            "company_id": self.env.company.id,
                            "user_id": self.env.user.id,
                            "create_uid": self.env.user.id,
                            "end_datetime": self.env.cr.now() + timedelta(minutes=5),
                            "reason": False,
                        }
                    ],
                )

    def test_exception_generation_multiple(self):
        self.env["account.lock_exception"].search([]).sudo().unlink()

        wizard = self.env["wizard.account.config.update.lock.date"].create(
            {
                "fiscalyear_lock_date": "2010-01-01",
                "tax_lock_date": "2010-01-01",
                "sale_lock_date": "2010-01-01",
                "purchase_lock_date": "2010-01-01",
            }
        )
        wizard.change_lock_date()

        self.assertRecordValues(
            self.env.company.account_config_id,
            [
                {
                    "fiscalyear_lock_date": fields.Date.from_string("2010-01-01"),
                    "tax_lock_date": fields.Date.from_string("2010-01-01"),
                    "sale_lock_date": fields.Date.from_string("2010-01-01"),
                    "purchase_lock_date": fields.Date.from_string("2010-01-01"),
                }
            ],
        )

        wizard = self.env["wizard.account.config.update.lock.date"].create(
            {
                "fiscalyear_lock_date": "2009-01-01",
                "tax_lock_date": "2009-01-01",
                "sale_lock_date": "2009-01-01",
                "purchase_lock_date": "2009-01-01",
                "exception_applies_to": "everyone",
                "exception_duration": "1h",
                "exception_reason": ":TestChangeLockDateWizard.test_exception_generation; remove",
            }
        )
        wizard.change_lock_date()

        exceptions = self.env["account.lock_exception"].search([])
        self.assertEqual(len(exceptions), 4)
        expected_exceptions = {
            frozendict(
                {
                    "lock_date_field": "fiscalyear_lock_date",
                    "lock_date": fields.Date.from_string("2009-01-01"),
                }
            ),
            frozendict(
                {
                    "lock_date_field": "tax_lock_date",
                    "lock_date": fields.Date.from_string("2009-01-01"),
                }
            ),
            frozendict(
                {
                    "lock_date_field": "sale_lock_date",
                    "lock_date": fields.Date.from_string("2009-01-01"),
                }
            ),
            frozendict(
                {
                    "lock_date_field": "purchase_lock_date",
                    "lock_date": fields.Date.from_string("2009-01-01"),
                }
            ),
        }
        created_exceptions = {
            frozendict(
                {
                    "lock_date_field": exception.lock_date_field,
                    "lock_date": exception.lock_date,
                }
            )
            for exception in exceptions
        }
        self.assertSetEqual(created_exceptions, expected_exceptions)

    def test_hard_lock_date(self):
        self.env["account.lock_exception"].search([]).sudo().unlink()

        self.env["wizard.account.config.update.lock.date"].create(
            {"hard_lock_date": "2010-01-01"}
        ).change_lock_date()
        self.assertEqual(
            self.env.company.account_config_id.hard_lock_date,
            fields.Date.from_string("2010-01-01"),
        )

        self.env["wizard.account.config.update.lock.date"].create(
            {"hard_lock_date": "2011-01-01"}
        ).change_lock_date()
        self.assertEqual(
            self.env.company.account_config_id.hard_lock_date,
            fields.Date.from_string("2011-01-01"),
        )

        wizard = self.env["wizard.account.config.update.lock.date"].create(
            {
                "hard_lock_date": "2009-01-01",
                "exception_applies_to": "everyone",
                "exception_duration": "1h",
                "exception_reason": ":TestChangeLockDateWizard.test_hard_lock_date",
            }
        )
        with self.assertRaises(UserError):
            wizard.change_lock_date()
        self.assertEqual(
            self.env.company.account_config_id.hard_lock_date,
            fields.Date.from_string("2011-01-01"),
        )

        wizard = self.env["wizard.account.config.update.lock.date"].create(
            {
                "hard_lock_date": False,
                "exception_applies_to": "everyone",
                "exception_duration": "1h",
                "exception_reason": ":TestChangeLockDateWizard.test_hard_lock_date",
            }
        )
        with self.assertRaises(UserError):
            wizard.change_lock_date()
        self.assertEqual(
            self.env.company.account_config_id.hard_lock_date,
            fields.Date.from_string("2011-01-01"),
        )

        self.assertEqual(self.env["account.lock_exception"].search_count([]), 0)

    def test_everyone_forever_exception(self):
        self.env["account.lock_exception"].search([]).sudo().unlink()

        for lock_date_field in SOFT_LOCK_DATE_FIELDS:
            with (
                self.subTest(lock_date_field=lock_date_field),
                closing(self.cr.savepoint()),
            ):
                self.env["wizard.account.config.update.lock.date"].create(
                    {lock_date_field: "2010-01-01"}
                ).change_lock_date()
                self.assertEqual(
                    self.env.company.account_config_id[lock_date_field],
                    fields.Date.from_string("2010-01-01"),
                )

                self.env["wizard.account.config.update.lock.date"].create(
                    {
                        lock_date_field: "2009-01-01",
                        "exception_applies_to": "everyone",
                        "exception_duration": "forever",
                        "exception_reason": ":TestChangeLockDateWizard.test_everyone_forever_exception; remove",
                    }
                ).change_lock_date()
                self.assertEqual(
                    self.env.company.account_config_id[lock_date_field],
                    fields.Date.from_string("2009-01-01"),
                )

                self.env["wizard.account.config.update.lock.date"].create(
                    {
                        lock_date_field: False,
                        "exception_applies_to": "everyone",
                        "exception_duration": "forever",
                        "exception_reason": ":TestChangeLockDateWizard.test_everyone_forever_exception; remove",
                    }
                ).change_lock_date()
                self.assertEqual(
                    self.env.company.account_config_id[lock_date_field], False
                )

                self.assertEqual(self.env["account.lock_exception"].search_count([]), 0)

    def test_a_manager_cannot_lock_another_company(self):
        company = self.company_data["company"]
        other_company = self.setup_other_company()["company"]
        manager = self.env["res.users"].create(
            {
                "name": "Manager of one company",
                "login": "lock_date_manager_one_company",
                "company_id": company.id,
                "company_ids": [Command.set(company.ids)],
                "group_ids": [
                    Command.set(
                        (
                            self.env.ref("account.group_account_manager")
                            + self.env.ref("base.group_user")
                        ).ids
                    )
                ],
            }
        )
        wizard = (
            self.env["wizard.account.config.update.lock.date"]
            .with_user(manager)
            .with_company(company)
            .create({"company_id": other_company.id})
        )
        wizard.fiscalyear_lock_date = "2019-12-31"

        with self.assertRaisesRegex(AccessError, "'write' access"):
            wizard.change_lock_date()
        self.assertFalse(other_company.account_config_id.fiscalyear_lock_date)

        own_wizard = (
            self.env["wizard.account.config.update.lock.date"]
            .with_user(manager)
            .with_company(company)
            .create({"fiscalyear_lock_date": "2019-12-31"})
        )
        own_wizard.change_lock_date()
        self.assertEqual(
            company.account_config_id.fiscalyear_lock_date,
            fields.Date.from_string("2019-12-31"),
        )

    def test_locking_seeds_the_fiscal_year_not_the_calendar_year(self):
        config = self.env.company.account_config_id
        config.write({"fiscalyear_last_month": "3", "fiscalyear_last_day": 31})
        wizard = self.env["wizard.account.config.update.lock.date"].create(
            {"fiscalyear_lock_date": "2025-03-31"}
        )

        self.assertEqual(
            wizard._get_current_period_dates("fiscalyear_lock_date"),
            (
                fields.Date.from_string("2024-04-01"),
                fields.Date.from_string("2025-03-31"),
            ),
        )

        config.write(
            {"fiscalyear_lock_date": "2024-06-30", "hard_lock_date": "2024-09-30"}
        )
        self.assertEqual(
            wizard._get_current_period_dates("fiscalyear_lock_date")[0],
            fields.Date.from_string("2024-10-01"),
        )
