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

    def test_an_approval_whose_operation_ran_cannot_be_taken_back(self):
        document = self._document()
        document.action_ship()
        self._approve(document)
        self.assertEqual(document.ship_count, 1)
        request = document.approval_request_id

        with self.assertRaisesRegex(UserError, "already went through"):
            request.with_user(self.approver_1).action_withdraw()
        self.assertEqual(request.state, "approved")

    def test_an_operation_run_by_hand_after_the_grant_counts_as_its_run(self):
        document = self._document()
        Gated = self.registry["approval.test.gated"]
        with patch.object(
            Gated, "_is_operation_run_on_approval", lambda self, operation: False
        ):
            document.action_ship()
            self._approve(document)
            request = document.approval_request_id
            self.assertEqual(document.ship_count, 0)
            self.assertFalse(request.date_operation_run)

            document.action_ship()

        self.assertEqual(document.ship_count, 1)
        self.assertTrue(request.date_operation_run)
        with self.assertRaisesRegex(UserError, "already went through"):
            request.with_user(self.approver_1).action_withdraw()

    def test_a_used_approval_gives_way_to_asking_for_the_next_operation(self):
        document = self._document()
        document.action_ship()
        shipped = document.approval_request_id
        self._approve(document)
        self.assertTrue(shipped.date_operation_run)

        document.action_bill()

        billed = document.approval_request_id
        self.assertNotEqual(billed, shipped)
        self.assertEqual((billed.operation, billed.state), ("bill", "pending"))
        self.assertEqual(shipped.state, "approved")
        self.assertEqual(document.bill_count, 0)

    def test_an_unused_approval_is_not_dropped_for_another_operation(self):
        document = self._document()
        document.runs_on_approval = False
        document.action_ship()
        shipped = document.approval_request_id
        self._approve(document)

        with self.assertRaisesRegex(UserError, "has not been used yet"):
            document.action_bill()
        self.assertEqual(document.approval_request_id, shipped)

    def test_a_reset_request_is_asked_about_the_document_as_it_is_now(self):
        document = self._document()
        document.action_ship()
        request = document.approval_request_id
        request.approver_ids.with_user(self.approver_1).with_context(
            skip_wizard=True
        ).action_refuse()
        request.action_reset_to_draft()

        document.amount_total = 250.0
        request.action_confirm()

        self.assertEqual(request.amount, 250.0)
        self._approve(document)
        self.assertEqual(document.ship_count, 1)
