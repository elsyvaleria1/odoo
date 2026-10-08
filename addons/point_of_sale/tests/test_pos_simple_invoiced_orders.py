import os
import time
from datetime import date
from unittest.mock import patch

import odoo
from odoo import fields

from odoo.addons.point_of_sale.tests.common import (
    PosCashRoundingSessionCommon,
    TestPoSCommon,
)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosSimpleInvoicedOrders(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product100 = cls.create_product("Product_100", cls.categ_basic, 100, 50)

    def test_01b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.cash_pm1, 100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.cash_pm1, 100),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 100,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 100,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.cash_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 100,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 100,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (100,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_pm1.journal_id.default_account_id.id,
                                        "partner_id": False,
                                        "debit": 100,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.cash_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 100,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [],
                },
            }
        )

    def test_02b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.bank_pm1,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.bank_pm1, 100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "journal_id": self.config.invoice_journal_id.id,
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                },
                            ],
                        },
                        "payments": [
                            (
                                (self.bank_pm1, 100),
                                {
                                    "journal_id": self.config.journal_id.id,
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 100,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 100,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ],
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "journal_id": self.config.journal_id.id,
                        "line_ids": [
                            {
                                "account_id": self.bank_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 100,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 100,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [],
                    "bank_payments": [
                        (
                            (100,),
                            {
                                "journal_id": self.bank_pm1.journal_id.id,
                                "line_ids": [
                                    {
                                        "account_id": self.bank_pm1.outstanding_account_id.id,
                                        "partner_id": False,
                                        "debit": 100,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.bank_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 100,
                                        "reconciled": True,
                                    },
                                ],
                            },
                        )
                    ],
                },
            }
        )

    def test_03b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.pay_later_pm, 100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "journal_id": self.config.invoice_journal_id.id,
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": False,
                                },
                            ],
                        },
                        "payments": [],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": False,
                    "cash_statement": [],
                    "bank_payments": [],
                },
            }
        )

    def test_04b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.bank_split_pm1,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.bank_split_pm1, 100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "journal_id": self.config.invoice_journal_id.id,
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                },
                            ],
                        },
                        "payments": [
                            (
                                (self.bank_split_pm1, 100),
                                {
                                    "journal_id": self.config.journal_id.id,
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 100,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 100,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ],
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "journal_id": self.config.journal_id.id,
                        "line_ids": [
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 100,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 100,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [],
                    "bank_payments": [
                        (
                            (100,),
                            {
                                "journal_id": self.bank_split_pm1.journal_id.id,
                                "line_ids": [
                                    {
                                        "account_id": self.bank_split_pm1.outstanding_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 100,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 100,
                                        "reconciled": True,
                                    },
                                ],
                            },
                        )
                    ],
                },
            }
        )

    def test_05b(self):
        self._run_test(
            {
                "payment_methods": self.cash_split_pm1,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.cash_split_pm1, 100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.cash_split_pm1, 100),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 100,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 100,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 100,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 100,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (100,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_split_pm1.journal_id.default_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 100,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 100,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [],
                },
            }
        )

    def test_10b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.cash_pm1, 200), (self.pay_later_pm, -100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                    "partially_reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.cash_pm1, 200),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 200,
                                            "reconciled": False,
                                            "partially_reconciled": True,
                                            "amount_residual": -100,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 200,
                                            "credit": 0,
                                            "reconciled": False,
                                            "amount_residual": 200,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.cash_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 200,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 200,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (200,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_pm1.journal_id.default_account_id.id,
                                        "partner_id": False,
                                        "debit": 200,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.cash_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 200,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [],
                },
            }
        )

    def test_11b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.bank_pm1 | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.bank_pm1, 200), (self.pay_later_pm, -100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                    "partially_reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.bank_pm1, 200),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 200,
                                            "reconciled": False,
                                            "partially_reconciled": True,
                                            "amount_residual": -100,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 200,
                                            "credit": 0,
                                            "reconciled": False,
                                            "amount_residual": 200,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.bank_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 200,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 200,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [],
                    "bank_payments": [
                        (
                            (200,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.bank_pm1.outstanding_account_id.id,
                                        "partner_id": False,
                                        "debit": 200,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.bank_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 200,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                },
            }
        )

    def test_12b(self):
        self._run_test(
            {
                "payment_methods": self.cash_split_pm1 | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [
                            (self.cash_split_pm1, 200),
                            (self.pay_later_pm, -100),
                        ],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                    "partially_reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.cash_split_pm1, 200),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 200,
                                            "reconciled": False,
                                            "partially_reconciled": True,
                                            "amount_residual": -100,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 200,
                                            "credit": 0,
                                            "reconciled": False,
                                            "amount_residual": 200,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 200,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 200,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (200,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_split_pm1.journal_id.default_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 200,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 200,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [],
                },
            }
        )

    def test_13b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1
                | self.bank_split_pm1
                | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [
                            (self.bank_split_pm1, 200),
                            (self.pay_later_pm, -100),
                        ],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                    "partially_reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.bank_split_pm1, 200),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 200,
                                            "reconciled": False,
                                            "partially_reconciled": True,
                                            "amount_residual": -100,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 200,
                                            "credit": 0,
                                            "reconciled": False,
                                            "amount_residual": 200,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 200,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 200,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [],
                    "bank_payments": [
                        (
                            (200,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.bank_split_pm1.outstanding_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 200,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 200,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                },
            }
        )

    def test_14b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.cash_pm1, 200), (self.cash_pm1, -100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.cash_pm1, 200),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 200,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 200,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                            (
                                (self.cash_pm1, -100),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 100,
                                            "credit": 0,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 0,
                                            "credit": 100,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.cash_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 100,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 100,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (100,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_pm1.journal_id.default_account_id.id,
                                        "partner_id": False,
                                        "debit": 100,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.cash_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 100,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [],
                },
            }
        )

    def test_15b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.bank_pm1,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.bank_pm1, 200), (self.cash_pm1, -100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.bank_pm1, 200),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 200,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 200,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                            (
                                (self.cash_pm1, -100),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 100,
                                            "credit": 0,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 0,
                                            "credit": 100,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.bank_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 200,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.cash_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 100,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 200,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 100,
                                "credit": 0,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (-100,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_pm1.journal_id.default_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 100,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.cash_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 100,
                                        "credit": 0,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [
                        (
                            (200,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.bank_pm1.outstanding_account_id.id,
                                        "partner_id": False,
                                        "debit": 200,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.bank_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 200,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                },
            }
        )

    def test_16b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.bank_split_pm1,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.bank_split_pm1, 200), (self.cash_pm1, -100)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.bank_split_pm1, 200),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 200,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 200,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                            (
                                (self.cash_pm1, -100),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 100,
                                            "credit": 0,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 0,
                                            "credit": 100,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 200,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.cash_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 100,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 100,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 200,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (-100,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_pm1.journal_id.default_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 100,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.cash_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 100,
                                        "credit": 0,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [
                        (
                            (200,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.bank_split_pm1.outstanding_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 200,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 200,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                },
            }
        )

    def test_17b(self):
        self._run_test(
            {
                "payment_methods": self.cash_split_pm1,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [
                            (self.cash_split_pm1, 200),
                            (self.cash_split_pm1, -100),
                        ],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": True,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.cash_split_pm1, 200),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 200,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 200,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                            (
                                (self.cash_split_pm1, -100),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 100,
                                            "credit": 0,
                                            "reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 0,
                                            "credit": 100,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 200,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 0,
                                "credit": 100,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 200,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 100,
                                "credit": 0,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (200,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_split_pm1.journal_id.default_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 200,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 200,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        ),
                        (
                            (-100,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_split_pm1.journal_id.default_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 100,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 100,
                                        "credit": 0,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        ),
                    ],
                    "bank_payments": [],
                },
            }
        )

    def test_18b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.cash_pm1, 50), (self.pay_later_pm, 50)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                    "amount_residual": 0,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": False,
                                    "partially_reconciled": True,
                                    "amount_residual": 50,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.cash_pm1, 50),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 50,
                                            "reconciled": True,
                                            "partially_reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 50,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.cash_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 50,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 50,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (50,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_pm1.journal_id.default_account_id.id,
                                        "partner_id": False,
                                        "debit": 50,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.cash_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 50,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [],
                },
            }
        )

    def test_19b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1 | self.bank_pm1 | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [(self.bank_pm1, 50), (self.pay_later_pm, 50)],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                    "amount_residual": 0,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": False,
                                    "partially_reconciled": True,
                                    "amount_residual": 50,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.bank_pm1, 50),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 50,
                                            "reconciled": True,
                                            "partially_reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 50,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.bank_pm1.receivable_account_id.id,
                                "partner_id": False,
                                "debit": 50,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 50,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [],
                    "bank_payments": [
                        (
                            (50,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.bank_pm1.outstanding_account_id.id,
                                        "partner_id": False,
                                        "debit": 50,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.bank_pm1.receivable_account_id.id,
                                        "partner_id": False,
                                        "debit": 0,
                                        "credit": 50,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                },
            }
        )

    def test_20b(self):
        self._run_test(
            {
                "payment_methods": self.cash_pm1
                | self.bank_split_pm1
                | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [
                            (self.bank_split_pm1, 50),
                            (self.pay_later_pm, 50),
                        ],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                    "amount_residual": 0,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": False,
                                    "partially_reconciled": True,
                                    "amount_residual": 50,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.bank_split_pm1, 50),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 50,
                                            "reconciled": True,
                                            "partially_reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 50,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 50,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 50,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [],
                    "bank_payments": [
                        (
                            (50,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.bank_split_pm1.outstanding_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 50,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 50,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                },
            }
        )

    def test_21b(self):
        self._run_test(
            {
                "payment_methods": self.cash_split_pm1 | self.pay_later_pm,
                "orders": [
                    {
                        "pos_order_lines_ui_args": [(self.product100, 1)],
                        "payments": [
                            (self.cash_split_pm1, 50),
                            (self.pay_later_pm, 50),
                        ],
                        "customer": self.customer,
                        "is_invoiced": True,
                        "uuid": "00100-010-0001",
                    },
                ],
                "journal_entries_before_closing": {
                    "00100-010-0001": {
                        "invoice": {
                            "line_ids": [
                                {
                                    "account_id": self.sales_account.id,
                                    "partner_id": self.customer.id,
                                    "debit": 0,
                                    "credit": 100,
                                    "reconciled": False,
                                    "amount_residual": 0,
                                },
                                {
                                    "account_id": self.c1_receivable.id,
                                    "partner_id": self.customer.id,
                                    "debit": 100,
                                    "credit": 0,
                                    "reconciled": False,
                                    "partially_reconciled": True,
                                    "amount_residual": 50,
                                },
                            ]
                        },
                        "payments": [
                            (
                                (self.cash_split_pm1, 50),
                                {
                                    "line_ids": [
                                        {
                                            "account_id": self.c1_receivable.id,
                                            "partner_id": self.customer.id,
                                            "debit": 0,
                                            "credit": 50,
                                            "reconciled": True,
                                            "partially_reconciled": True,
                                        },
                                        {
                                            "account_id": self.pos_receivable_account.id,
                                            "partner_id": False,
                                            "debit": 50,
                                            "credit": 0,
                                            "reconciled": False,
                                        },
                                    ]
                                },
                            ),
                        ],
                    }
                },
                "journal_entries_after_closing": {
                    "session_journal_entry": {
                        "line_ids": [
                            {
                                "account_id": self.c1_receivable.id,
                                "partner_id": self.customer.id,
                                "debit": 50,
                                "credit": 0,
                                "reconciled": True,
                            },
                            {
                                "account_id": self.pos_receivable_account.id,
                                "partner_id": False,
                                "debit": 0,
                                "credit": 50,
                                "reconciled": True,
                            },
                        ],
                    },
                    "cash_statement": [
                        (
                            (50,),
                            {
                                "line_ids": [
                                    {
                                        "account_id": self.cash_split_pm1.journal_id.default_account_id.id,
                                        "partner_id": self.customer.id,
                                        "debit": 50,
                                        "credit": 0,
                                        "reconciled": False,
                                    },
                                    {
                                        "account_id": self.c1_receivable.id,
                                        "partner_id": self.customer.id,
                                        "debit": 0,
                                        "credit": 50,
                                        "reconciled": True,
                                    },
                                ]
                            },
                        )
                    ],
                    "bank_payments": [],
                },
            }
        )


@odoo.tests.tagged("post_install", "-at_install")
class TestPosOrderInvoiceDate(PosCashRoundingSessionCommon):
    def test_invoice_date_treats_order_datetime_as_utc(self):
        order = self._create_bare_order(
            partner_id=self.partner_mobt.id,
            date_order=fields.Datetime.to_datetime("2026-09-13 01:00:00"),
        ).with_context(tz="America/Mexico_City")
        try:
            with patch.dict(os.environ, TZ="America/Los_Angeles"):
                time.tzset()
                values = order._prepare_invoice_vals()
        finally:
            time.tzset()

        self.assertEqual(values["invoice_date"], date(2026, 9, 12))

    def test_invoice_date_under_normal_utc_process(self):
        order = self._create_bare_order(
            partner_id=self.partner_mobt.id, date_order="2026-09-13 01:00:00"
        )
        for timezone, expected in (
            ("UTC", date(2026, 9, 13)),
            ("America/Mexico_City", date(2026, 9, 12)),
            ("Asia/Tokyo", date(2026, 9, 13)),
        ):
            with self.subTest(timezone=timezone):
                self.assertEqual(os.environ.get("TZ"), "UTC")
                self.assertEqual(
                    order.with_context(tz=timezone)._prepare_invoice_vals()[
                        "invoice_date"
                    ],
                    expected,
                )
