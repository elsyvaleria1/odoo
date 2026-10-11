from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common_report_engine import TestAccountReportsCommon


@tagged("post_install", "-at_install")
class TestDeferredFleet(TestAccountReportsCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref(
            "resource_asset_vehicle.fleet_group_manager"
        )
        cls.expense_accounts = [
            cls.env["account.account"].create(
                {
                    "name": f"Expense {i}",
                    "code": f"EXP{i}",
                    "account_type": "expense",
                }
            )
            for i in range(3)
        ]

        cls.company.account_config_id.deferred_expense_journal_id = cls.company_data[
            "default_journal_misc"
        ].id
        cls.company.account_config_id.deferred_expense_account_id = cls.company_data[
            "default_account_deferred_expense"
        ].id

        cls.expense_lines = [
            [
                cls.expense_accounts[0],
                1000,
                "2023-01-01",
                "2023-04-30",
            ],
            [
                cls.expense_accounts[0],
                1050,
                "2023-01-16",
                "2023-04-30",
            ],
            [
                cls.expense_accounts[1],
                1225,
                "2023-01-01",
                "2023-04-15",
            ],
            [
                cls.expense_accounts[2],
                1680,
                "2023-01-21",
                "2023-04-14",
            ],
            [
                cls.expense_accounts[2],
                225,
                "2023-04-01",
                "2023-04-15",
            ],
        ]

        cls.batmobile, cls.batpod = cls.env["resource.resource"].create(
            [
                {
                    "name": name,
                    "kind_id": cls.env.ref("base.kind_vehicle").id,
                    "rate_ids": [
                        Command.create(
                            {
                                "date_from": fields.Date.from_string("2022-01-01"),
                                "rate": rate,
                            }
                        )
                    ],
                }
                for name, _vehicle_type, rate in [
                    ("Batmobile", "car", 31.0),
                    ("Batpod", "bike", 56.0),
                ]
            ]
        )

    def test_deferred_fleet_on_validation_mode(self):
        move = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "date": "2023-01-01",
                "invoice_date": "2023-01-01",
                "journal_id": self.company_data["default_journal_purchase"].id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1,
                            "account_id": self.expense_accounts[0].id,
                            "price_unit": 1000,
                            "deferred_start_date": "2023-02-01",
                            "deferred_end_date": "2023-02-28",
                            "asset_id": self.batmobile.id,
                        }
                    ),
                ],
            }
        )
        move.action_post()
        self.assertRecordValues(
            move.deferred_move_ids.line_ids,
            [{"asset_id": self.batmobile.id} for _ in range(4)],
        )

    def test_deferred_fleet_manually_and_grouped_mode(self):
        self.company.account_config_id.generate_deferred_expense_entries_method = (
            "manual"
        )
        self.company.account_config_id.deferred_expense_amount_computation_method = (
            "month"
        )

        def get_line(vehicle, account, amount):
            return Command.create(
                {
                    "quantity": 1,
                    "account_id": account.id,
                    "price_unit": amount,
                    "deferred_start_date": "2023-01-01",
                    "deferred_end_date": "2023-10-31",
                    "asset_id": vehicle.id if vehicle else False,
                }
            )

        self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "date": "2023-01-01",
                "invoice_date": "2023-01-01",
                "journal_id": self.company_data["default_journal_purchase"].id,
                "invoice_line_ids": [
                    get_line(self.batmobile, self.expense_accounts[0], 1000),
                    get_line(self.batpod, self.expense_accounts[0], 2000),
                    get_line(self.batpod, self.expense_accounts[1], 5000),
                    get_line(self.batpod, self.expense_accounts[1], 10000),
                    get_line(False, self.expense_accounts[1], 10000),
                    get_line(False, self.expense_accounts[1], 10000),
                ],
            }
        ).action_post()
        options = self._generate_options(
            self.env.ref("account.deferred_expense_report"),
            "2023-01-01",
            "2023-01-31",
        )
        deferral_entries = self.env[
            "account.deferred.expense.report.handler"
        ]._generate_deferral_entry(options)
        expected_values = [
            {
                "account_id": self.expense_accounts[0].id,
                "asset_id": self.batmobile.id,
                "balance": -1000,
            },
            {
                "account_id": self.expense_accounts[0].id,
                "asset_id": self.batmobile.id,
                "balance": 100,
            },
            {
                "account_id": self.expense_accounts[0].id,
                "asset_id": self.batpod.id,
                "balance": -2000,
            },
            {
                "account_id": self.expense_accounts[0].id,
                "asset_id": self.batpod.id,
                "balance": 200,
            },
            {
                "account_id": self.expense_accounts[1].id,
                "asset_id": self.batpod.id,
                "balance": -15000,
            },
            {
                "account_id": self.expense_accounts[1].id,
                "asset_id": self.batpod.id,
                "balance": 1500,
            },
            {
                "account_id": self.expense_accounts[1].id,
                "asset_id": False,
                "balance": -20000,
            },
            {
                "account_id": self.expense_accounts[1].id,
                "asset_id": False,
                "balance": 2000,
            },
            {
                "account_id": self.company.account_config_id.deferred_expense_account_id.id,
                "asset_id": self.batmobile.id,
                "balance": 900,
            },
            {
                "account_id": self.company.account_config_id.deferred_expense_account_id.id,
                "asset_id": self.batpod.id,
                "balance": 13500 + 1800,
            },
            {
                "account_id": self.company.account_config_id.deferred_expense_account_id.id,
                "asset_id": False,
                "balance": 18000,
            },
        ]
        for line, expected in zip(
            deferral_entries[0].line_ids, expected_values, strict=True
        ):
            self.assertRecordValues(
                line,
                [
                    {
                        "account_id": expected["account_id"],
                        "asset_id": expected["asset_id"],
                        "balance": expected["balance"],
                    }
                ],
            )
