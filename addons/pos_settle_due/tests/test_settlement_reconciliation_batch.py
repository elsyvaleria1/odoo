import logging
from unittest.mock import patch

import odoo
from odoo.tests import counting_statements

from odoo.addons.pos_settle_due.tests.test_receivable_account_reconciliation import (
    TestPOSCustomerAccountReconciliation,
)

_logger = logging.getLogger(__name__)


@odoo.tests.tagged("-at_install", "post_install")
class TestSettlementReconciliationBatch(TestPOSCustomerAccountReconciliation):
    def setUp(self):
        super().setUp()
        self.partners = self.env["res.partner"].create(
            [{"name": f"Settling customer {index}"} for index in range(20)]
        )
        self.order_data = [
            {
                "pos_order_lines_ui_args": [(self.product_a, 1)],
                "payments": [(self.pay_later_pm, 1150)],
                "customer": partner,
                "is_invoiced": False,
            }
            for partner in self.partners
        ]

    def test_twenty_settlements_reconcile_in_one_plan(self):
        session1 = self.open_new_session()
        orders = self._create_paid_orders()
        session1.close_session_from_ui()
        session2 = self.open_new_session()
        self._create_settle_order(orders)

        AccountMoveLine = type(self.env["account.move.line"])
        reconcile_plan = AccountMoveLine._reconcile_plan
        with (
            patch.object(
                AccountMoveLine,
                "_reconcile_plan",
                autospec=True,
                side_effect=reconcile_plan,
            ) as plan,
        ):
            self.env.flush_all()
            with counting_statements(self.env.cr) as counted:
                session2.close_session_from_ui()
                statements = counted.count
        _logger.debug(
            "closing with 20 settlements: %s statements, %s plans",
            statements,
            plan.call_count,
        )

        self.assertEqual(session2.state, "closed")
        self.assertEqual(plan.call_count, 2)
        for partner in self.partners:
            self.assertFalse(self._get_unreconciled_moves(partner), partner.name)
