from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.approval.tests.common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestGateRunStamp(ApprovalCommon):
    def setUp(self):
        super().setUp()
        self.category = self._make_category(
            name=f"Run Stamp {self.id()}", approvers=[self.approver_1]
        )

    def _document(self):
        return self.env["approval.test.gated"].create(
            {
                "name": "Run Stamp",
                "partner_id": self.partner.id,
                "amount_total": 100.0,
                "test_category_id": self.category.id,
            }
        )

    def _approve(self, document):
        document.approval_request_id.with_user(self.approver_1).action_approve()

    def test_a_grant_whose_operation_fails_is_not_counted_as_run(self):
        document = self._document()
        document.action_ship()
        request = document.approval_request_id

        def failing_ship(records, shipped):
            raise UserError("Nothing to ship")

        with patch.object(self.registry["approval.test.gated"], "_ship", failing_ship):
            self._approve(document)
        self.assertEqual(document.approval_state, "approved")
        self.assertEqual(document.ship_count, 0)
        self.assertFalse(request.date_operation_run)
        self.assertTrue(
            any(
                "could not go through" in body
                for body in document.message_ids.mapped("body")
            )
        )

    def test_a_grant_whose_operation_runs_is_counted_as_run(self):
        document = self._document()
        document.action_ship()
        self._approve(document)
        self.assertEqual(document.ship_count, 1)
        self.assertTrue(document.approval_request_id.date_operation_run)

    def test_a_category_set_after_the_flag_was_read_still_gates(self):
        document = self._document()
        document.test_category_id = False
        self.assertFalse(document.approval_required)
        document.test_category_id = self.category
        document.action_ship()
        self.assertEqual(document.ship_count, 0)
        self.assertTrue(document.approval_request_id)
