from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.approval.tests.common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestOwnDecision(ApprovalCommon):
    def setUp(self):
        super().setUp()
        self.category = self._make_category(
            name=f"Own Decision {self.id()}",
            approvers=[
                (self.owner_user, False, 10),
                (self.approver_1, False, 20),
                (self.approver_2, False, 30),
            ],
            approval_minimum=1,
        )

    def _gated(self, user=None):
        return self.env["approval.test.gated"].create(
            {
                "name": "Own Decision Gated",
                "partner_id": self.partner.id,
                "amount_total": 100.0,
                "test_category_id": self.category.id,
                "user_id": (user or self.env["res.users"]).id,
            }
        )

    def _exception(self, user, kind, **vals):
        return (
            self.env["ir.access.exception"]
            .sudo()
            .create(
                {
                    "user_id": user.id,
                    "kind": kind,
                    "res_model": "approval.category",
                    "res_id": self.category.id,
                    "reason": "Covering while the category is reviewed",
                    "reviewer_ids": [(6, 0, self.manager_user.ids)],
                    "date_to": fields.Datetime.now() + timedelta(days=30),
                    **vals,
                }
            )
        )

    def _row(self, request, user):
        return request.approver_ids.filtered(lambda row: row.user_id == user)

    def _uses(self, exception):
        return self.env["ir.access.log"].search_count(
            [
                ("event", "=", "exception_used"),
                ("cause_model", "=", "ir.access.exception"),
                ("cause_res_id", "=", exception.id),
            ]
        )

    def test_the_declared_requester_is_not_asked(self):
        document = self._gated(user=self.approver_1)
        document.with_user(self.owner_user).sudo().action_create_approval_request()
        request = document.approval_request_id
        self.assertEqual(request.requester_id, self.approver_1)
        self.assertFalse(self._row(request, self.approver_1))
        self.assertFalse(self._row(request, self.owner_user))

    def test_an_exception_lets_the_declared_requester_decide_and_is_logged(self):
        exception = self._exception(self.approver_1, "requester_exclusion")
        document = self._gated(user=self.approver_1)
        document.with_user(self.owner_user).sudo().action_create_approval_request()
        request = document.approval_request_id
        row = self._row(request, self.approver_1)
        self.assertTrue(row)
        request.with_user(self.approver_1).action_approve(row)
        self.assertEqual(request.state, "approved")
        self.assertEqual(self._uses(exception), 1)
        self.assertEqual(exception.use_count, 1)

    def test_a_delegate_deciding_the_owners_own_row_is_refused(self):
        self.category.allow_self_approval = True
        request = self._prepare_request(self.category)
        row = self._row(request, self.owner_user)
        self.assertTrue(row, "allowed, the owner is asked")
        self.category.allow_self_approval = False
        delegate = new_test_user(
            self.env, login="own_decision_delegate", groups="base.group_user"
        )
        self._delegate_row(row, delegate)
        with self.assertRaises(AccessError):
            request.with_user(delegate).action_approve(row)

    def test_an_exception_lets_the_owner_decide_and_a_lapsed_one_does_not(self):
        exception = self._exception(self.owner_user, "self_approval")
        request = self._prepare_request(self.category)
        row = self._row(request, self.owner_user)
        self.assertTrue(row, "the exception keeps the owner on the step")
        exception.sudo().write(
            {
                "date_from": fields.Datetime.now() - timedelta(days=60),
                "date_to": fields.Datetime.now() - timedelta(days=1),
            }
        )
        with self.assertRaises(AccessError):
            request.with_user(self.owner_user).action_approve(row)
        self.assertEqual(self._uses(exception), 0)

    def test_nobody_may_delegate_to_the_declared_requester(self):
        buyer = new_test_user(
            self.env, login="own_decision_buyer", groups="base.group_user"
        )
        document = self._gated(user=buyer)
        document.with_user(self.owner_user).sudo().action_create_approval_request()
        row = self._row(document.approval_request_id, self.approver_1)
        with self.assertRaises(ValidationError):
            self._delegate_row(row, buyer)
