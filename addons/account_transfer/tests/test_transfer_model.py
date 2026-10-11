from datetime import datetime
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account_transfer.tests.account_transfer_test_classes import (
    AccountAutoTransferTestCase,
)


@tagged("post_install", "-at_install")
class TransferModelTestFunctionalCase(AccountAutoTransferTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.functional_transfer = cls.env["account.transfer.model"].create(
            {
                "name": "Test Functional Model",
                "date_start": "2019-01-01",
                "date_stop": "2019-12-31",
                "journal_id": cls.journal.id,
                "account_ids": [
                    Command.link(account.id) for account in cls.origin_accounts
                ],
                "line_ids": [
                    Command.create(
                        {
                            "account_id": account.id,
                            "percent": 20,
                        }
                    )
                    for account in cls.destination_accounts
                ],
            }
        )
        neutral_account = cls.env["account.account"].create(
            {
                "name": "Neutral Account",
                "code": "NEUT",
                "account_type": "income",
            }
        )
        cls.dates = ("2019-01-15", "2019-02-15")
        for date in cls.dates:
            for account in cls.origin_accounts:
                cls._create_basic_move(
                    cls,
                    deb_account=account.id,
                    cred_account=neutral_account.id,
                    amount=4000,
                    date_str=date,
                )

    def test_lines_on_move(self):
        self.functional_transfer.action_perform_auto_transfer()
        for account in self.origin_accounts:
            self.assertEqual(
                sum(
                    self.env["account.move.line"]
                    .search([("account_id", "=", account.id)])
                    .mapped("balance")
                ),
                1600,
            )
        for account in self.destination_accounts:
            self.assertEqual(
                sum(
                    self.env["account.move.line"]
                    .search([("account_id", "=", account.id)])
                    .mapped("balance")
                ),
                3200,
            )
            for date in self.dates:
                amls = self.env["account.move.line"].search(
                    [
                        ("account_id", "=", account.id),
                        (
                            "date",
                            "=",
                            fields.Date.to_date(date) + relativedelta(day=31),
                        ),
                    ]
                )
                self.assertEqual(len(amls), 1)


@tagged("post_install", "-at_install")
class TransferModelTestCase(AccountAutoTransferTestCase):
    @patch(
        "odoo.addons.account_transfer.models.transfer_model.AccountTransferModel.action_perform_auto_transfer"
    )
    def test_action_cron_auto_transfer(self, patched):
        TransferModel = self.env["account.transfer.model"]
        TransferModel.create(
            {
                "name": "Test Cron Model",
                "date_start": "2019-01-01",
                "date_stop": datetime.today() + relativedelta(months=1),
                "journal_id": self.journal.id,
            }
        )
        TransferModel.action_cron_auto_transfer()
        patched.assert_called_once()

    @patch(
        "odoo.addons.account_transfer.models.transfer_model.AccountTransferModel._create_or_update_move_for_period"
    )
    @freeze_time("2022-01-01")
    def test_action_perform_auto_transfer(self, patched):
        self.transfer_model.date_start = datetime.strftime(
            datetime.today() + relativedelta(day=1), "%Y-%m-%d"
        )
        self.transfer_model.action_perform_auto_transfer()
        patched.assert_not_called()

        master_ids, slave_ids = self._create_accounts(1, 2)
        self.transfer_model.write({"account_ids": [Command.link(master_ids.id)]})

        self.transfer_model.action_perform_auto_transfer()
        patched.assert_not_called()

        self.transfer_model.write(
            {
                "line_ids": [
                    Command.create({"percent": 50.0, "account_id": slave_ids[0].id}),
                    Command.create({"percent": 50.0, "account_id": slave_ids[1].id}),
                ]
            }
        )

        self.transfer_model.action_perform_auto_transfer()
        patched.assert_called_once()

        transfer_model = self.transfer_model.copy()
        transfer_model.write(
            {"date_start": transfer_model.date_start + relativedelta(months=-12)}
        )
        initial_call_count = patched.call_count
        transfer_model.action_perform_auto_transfer()
        self.assertEqual(
            initial_call_count + 13,
            patched.call_count,
            "13 more calls should have been done",
        )

    @patch(
        "odoo.addons.account_transfer.models.transfer_model.AccountTransferModel._prepare_transfer_move_line_vals_list"
    )
    def test_create_or_update_move_for_period(
        self, patched_get_transfer_move_lines_values
    ):
        master_ids, _ = self._create_accounts(2, 0)
        next_move_date = self.transfer_model._get_next_move_date(
            self.transfer_model.date_start
        )
        patched_get_transfer_move_lines_values.return_value = [
            {
                "account_id": master_ids[0].id,
                "date_maturity": next_move_date,
                "credit": 250.0,
            },
            {
                "account_id": master_ids[1].id,
                "date_maturity": next_move_date,
                "debit": 250.0,
            },
        ]

        created_move = self.transfer_model._create_or_update_move_for_period(
            self.transfer_model.date_start, next_move_date
        )
        self.assertEqual(len(created_move.line_ids), 2)
        self.assertRecordValues(
            created_move,
            [
                {
                    "date": next_move_date,
                    "journal_id": self.transfer_model.journal_id.id,
                    "transfer_model_id": self.transfer_model.id,
                }
            ],
        )
        self.assertRecordValues(
            created_move.line_ids.filtered(lambda l: l.credit),
            [
                {
                    "account_id": master_ids[0].id,
                    "date_maturity": next_move_date,
                    "credit": 250.0,
                }
            ],
        )
        self.assertRecordValues(
            created_move.line_ids.filtered(lambda l: l.debit),
            [
                {
                    "account_id": master_ids[1].id,
                    "date_maturity": next_move_date,
                    "debit": 250.0,
                }
            ],
        )

        patched_get_transfer_move_lines_values.return_value = [
            {
                "account_id": master_ids[0].id,
                "date_maturity": next_move_date,
                "credit": 78520.0,
            },
            {
                "account_id": master_ids[1].id,
                "date_maturity": next_move_date,
                "debit": 78520.0,
            },
        ]

        amount_of_moves = self.env["account.move"].search_count([])
        amount_of_move_lines = self.env["account.move.line"].search_count([])
        updated_move = self.transfer_model._create_or_update_move_for_period(
            self.transfer_model.date_start, next_move_date
        )
        self.assertEqual(
            amount_of_moves,
            self.env["account.move"].search_count([]),
            "No move have been created",
        )
        self.assertEqual(
            amount_of_move_lines,
            self.env["account.move.line"].search_count([]),
            "No move line have been created (in fact yes but the old ones have been deleted)",
        )
        self.assertEqual(updated_move, created_move, "Existing move has been updated")
        self.assertRecordValues(
            updated_move.line_ids.filtered(lambda l: l.credit),
            [
                {
                    "account_id": master_ids[0].id,
                    "date_maturity": next_move_date,
                    "credit": 78520.0,
                }
            ],
        )
        self.assertRecordValues(
            updated_move.line_ids.filtered(lambda l: l.debit),
            [
                {
                    "account_id": master_ids[1].id,
                    "date_maturity": next_move_date,
                    "debit": 78520.0,
                }
            ],
        )

    def test_get_move_for_period(self):
        date_to_test = datetime.strptime("2019-06-30", "%Y-%m-%d").date()
        move_for_period = self.transfer_model._get_move_for_period(date_to_test)
        self.assertIsNone(move_for_period, "No move is generated yet")

        move_date = self.transfer_model._get_next_move_date(
            self.transfer_model.date_start
        )
        already_generated_move = self.env["account.move"].create(
            {
                "date": move_date,
                "journal_id": self.journal.id,
                "transfer_model_id": self.transfer_model.id,
            }
        )
        move_for_period = self.transfer_model._get_move_for_period(date_to_test)
        self.assertEqual(
            move_for_period,
            already_generated_move,
            "Should be equal to the already generated move",
        )

        date_to_test += relativedelta(days=1)
        move_for_period = self.transfer_model._get_move_for_period(date_to_test)
        self.assertIsNone(move_for_period, "The generated move is for the next period")

        date_to_test += relativedelta(days=1)
        move_for_period = self.transfer_model._get_move_for_period(date_to_test)
        self.assertIsNone(
            move_for_period, "No move is generated yet for the next period"
        )

    @freeze_time("2019-12-01")
    def test_determine_start_date(self):
        start_date = self.transfer_model._get_start_date()
        self.assertEqual(
            start_date,
            self.transfer_model.date_start,
            "No moves generated yet, start date should be the start date of the transfer model",
        )

        move = self._create_basic_move(
            date_str="2019-07-01",
            journal_id=self.journal.id,
            transfer_model_id=self.transfer_model.id,
            posted=False,
        )
        start_date = self.transfer_model._get_start_date()
        self.assertEqual(
            start_date,
            self.transfer_model.date_start,
            "A move generated but not posted, start date should be the start date of the transfer model",
        )

        move.action_post()
        start_date = self.transfer_model._get_start_date()
        self.assertEqual(
            start_date,
            self.transfer_model.date_start,
            "A move posted, start date should sill be the start_date of the transfer_model",
        )

        lock_date = fields.Date.to_date("2019-08-31")
        self.company.account_config_id.fiscalyear_lock_date = lock_date
        start_date = self.transfer_model._get_start_date()
        self.assertEqual(
            start_date,
            lock_date.replace(day=1),
            "After setting a fiscal year lock date, start date should become the first day of the month of the lock date",
        )

    def test_get_next_move_date(self):
        experimentations = {
            (1, "month"): [
                (self.transfer_model.date_start, "2019-06-30"),
                (fields.Date.to_date("2019-01-29"), "2019-02-27"),
                (fields.Date.to_date("2019-01-30"), "2019-02-27"),
                (fields.Date.to_date("2019-01-31"), "2019-02-27"),
                (fields.Date.to_date("2019-02-28"), "2019-03-27"),
                (fields.Date.to_date("2019-12-31"), "2020-01-30"),
            ],
            (3, "month"): [
                (self.transfer_model.date_start, "2019-08-31"),
                (fields.Date.to_date("2019-01-31"), "2019-04-29"),
                (fields.Date.to_date("2019-02-28"), "2019-05-27"),
                (fields.Date.to_date("2019-12-31"), "2020-03-30"),
            ],
            (1, "year"): [
                (self.transfer_model.date_start, "2020-05-31"),
                (fields.Date.to_date("2019-01-31"), "2020-01-30"),
                (fields.Date.to_date("2019-02-28"), "2020-02-27"),
                (fields.Date.to_date("2019-12-31"), "2020-12-30"),
            ],
        }

        for (interval, unit), dates in experimentations.items():
            self.transfer_model.write(
                {"repeat_interval": interval, "repeat_unit": unit}
            )
            for start_date, expected_date_str in dates:
                next_date = self.transfer_model._get_next_move_date(start_date)
                self.assertEqual(
                    next_date,
                    fields.Date.to_date(expected_date_str),
                    "Next date from %s should be %s"
                    % (str(next_date), expected_date_str),
                )

    def test_check_line_ids_percents(self):
        with self.assertRaises(ValidationError):
            transfer_model_lines = []
            for i, percent in enumerate((50.0, 50.01)):
                transfer_model_lines.append(
                    Command.create(
                        {
                            "percent": percent,
                            "account_id": self.destination_accounts[i].id,
                        }
                    )
                )
            self.transfer_model.write(
                {
                    "account_ids": [Command.link(ma.id) for ma in self.origin_accounts],
                    "line_ids": transfer_model_lines,
                }
            )

    def test_unlink_of_transfer_with_no_moves(self):

        self.transfer_model.write(
            {
                "account_ids": [Command.link(self.origin_accounts[0].id)],
                "line_ids": [
                    Command.create(
                        {"percent": 100, "account_id": self.destination_accounts[0].id}
                    )
                ],
            }
        )
        self.transfer_model.action_enable()

        self.assertEqual(self.transfer_model.move_ids_count, 0)
        self.transfer_model.unlink()

    def test_error_unlink_of_transfer_with_moves(self):

        self.transfer_model.write(
            {
                "date_start": datetime.today() - relativedelta(day=1),
                "date_stop": False,
                "repeat_interval": 1,
                "repeat_unit": "year",
                "account_ids": [
                    Command.link(self.company_data["default_account_revenue"].id)
                ],
                "line_ids": [
                    Command.create(
                        {"percent": 100, "account_id": self.destination_accounts[0].id}
                    )
                ],
            }
        )
        self.transfer_model.action_enable()

        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": datetime.today(),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line1",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "price_unit": 1000.0,
                        }
                    ),
                ],
            }
        ).action_post()

        self.transfer_model.action_perform_auto_transfer()

        error_message = "You cannot delete a transfer model that has draft moves*"
        with self.assertRaisesRegex(UserError, error_message):
            self.transfer_model.unlink()

        self.transfer_model.move_ids[0].action_post()

        error_message = "You cannot delete a transfer model that has posted moves*"
        with self.assertRaisesRegex(UserError, error_message):
            self.transfer_model.unlink()

    def test_disable_transfer_when_archived(self):

        self.transfer_model.action_enable()
        self.assertEqual(self.transfer_model.state, "in_progress")

        self.transfer_model.action_archive()
        self.assertEqual(self.transfer_model.state, "disabled")

    @freeze_time("2022-01-01")
    def test_compute_transfer_lines_100_percent_transfer(self):
        self.transfer_model.date_start = datetime.strftime(
            datetime.today() + relativedelta(day=1), "%Y-%m-%d"
        )

        _, slave_ids = self._create_accounts(0, 3)
        self.transfer_model.write(
            {
                "account_ids": [
                    Command.link(self.company_data["default_account_revenue"].id)
                ],
                "line_ids": [
                    Command.create({"percent": 15, "account_id": slave_ids[0].id}),
                    Command.create({"percent": 42.50, "account_id": slave_ids[1].id}),
                    Command.create({"percent": 42.50, "account_id": slave_ids[2].id}),
                ],
            }
        )
        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": datetime.today(),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line_xyz",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "price_unit": 410.34,
                        }
                    ),
                ],
            }
        ).action_post()
        self.transfer_model.action_enable()
        self.transfer_model.action_perform_auto_transfer()
        lines = self.transfer_model.move_ids.line_ids
        self.assertAlmostEqual(
            lines.filtered(
                lambda l: l.account_id == self.company_data["default_account_revenue"]
            ).debit,
            410.34,
        )
        self.assertAlmostEqual(
            lines.filtered(lambda l: l.account_id == slave_ids[0]).credit, 61.55
        )
        self.assertAlmostEqual(
            lines.filtered(lambda l: l.account_id == slave_ids[1]).credit, 174.39
        )
        self.assertAlmostEqual(
            lines.filtered(lambda l: l.account_id == slave_ids[2]).credit, 174.4
        )
