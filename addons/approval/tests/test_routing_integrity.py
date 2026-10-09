from datetime import date, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .common import ApprovalCommon, pool_step


def listed_step(users, minimum=1, **step_vals):
    return pool_step(
        [(user.id, False, 10 * (index + 1)) for index, user in enumerate(users)],
        minimum=minimum,
        counts_added_approvers=False,
        **step_vals,
    )


@tagged("post_install", "-at_install")
class TestRoutingIntegrity(ApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        approver_group = cls.env.ref("approval.group_approval_approver")
        cls.delegate_user, cls.successor = (
            cls.env["res.users"].create(
                {
                    "name": name,
                    "login": f"routing_integrity_{name.lower().replace(' ', '_')}",
                    "email": f"{name.lower().replace(' ', '.')}@routing.test",
                    "group_ids": [Command.link(approver_group.id)],
                }
            )
            for name in ("Stand In", "Successor")
        )

    def _category(self, steps, **vals):
        return self.env["approval.category"].create(
            {
                "name": f"Routing {self.id()}",
                "sequence_code": self._next_sequence_code(),
                "step_ids": steps,
                **vals,
            }
        )

    def _row(self, request, user):
        return request.approver_ids.filtered(lambda row: row.user_id == user)

    def _delegate_with_wizard(self, principal, delegate):
        return (
            self.env["wizard.approval.approver.delegate"]
            .with_user(principal)
            .create(
                {
                    "delegate_id": delegate.id,
                    "start_date": date.today(),
                    "end_date": date.today() + timedelta(days=3),
                }
            )
            .action_confirm()
        )

    def test_a_change_after_which_no_step_applies_is_refused(self):
        category = self._category(
            listed_step(
                [self.approver_1],
                name="Urgent",
                condition_field="priority",
                operator="gte",
                threshold=2,
            )
        )
        request = self._prepare_request(category, priority="2")
        self.assertEqual(request.approval_minimum, 1)

        with self.assertRaises(UserError):
            request.with_user(self.owner_user).write({"priority": "0"})

        request.invalidate_recordset()
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.approval_minimum, 1)
        self.assertEqual(request.approver_ids.user_id, self.approver_1)

    def test_the_delegate_wizard_skips_a_request_its_delegate_is_for(self):
        category = self._category(listed_step([self.approver_1]))
        for_delegate = self._prepare_request(
            category, requester_id=self.delegate_user.id
        )
        other = self._prepare_request(category)

        result = self._delegate_with_wizard(self.approver_1, self.delegate_user)

        self.assertEqual(result["params"]["type"], "warning")
        self.assertFalse(for_delegate.approver_ids.delegate_id)
        self.assertEqual(other.approver_ids.delegate_id, self.delegate_user)

    def test_an_owner_allowed_to_approve_staffs_their_own_step(self):
        category = self._category(
            listed_step([self.owner_user]), allow_self_approval=True
        )
        request = self._prepare_request(category)
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.approver_ids.user_id, self.owner_user)

    def test_a_required_member_of_an_advisory_step_does_not_hold_the_request(self):
        category = self._category(
            listed_step([self.approver_1])
            + pool_step(
                [(self.approver_2.id, True, 10)],
                name="Advice",
                sequence=20,
                advisory=True,
                counts_added_approvers=False,
            )
        )
        request = self._prepare_request(category)
        self.assertTrue(self._row(request, self.approver_2).required)

        request.with_user(self.approver_1).action_approve()

        self.assertEqual(request.state, "approved")

    def test_without_steps_a_required_approver_still_holds_the_request(self):
        category = self._make_category(with_pool=False, approval_minimum=1)
        request = self._prepare_request(category, confirm=False)
        self.env["approval.approver"].create(
            [
                {"request_id": request.id, "user_id": self.approver_1.id},
                {
                    "request_id": request.id,
                    "user_id": self.approver_2.id,
                    "required": True,
                },
            ]
        )
        request.action_confirm()
        self.assertFalse(request.approver_ids.step_ids)

        request.with_user(self.approver_1).action_approve()
        self.assertEqual(request.state, "pending")

        request.with_user(self.approver_2).action_approve()
        self.assertEqual(request.state, "approved")

    def test_an_archived_member_is_not_asked(self):
        category = self._category(listed_step([self.approver_1, self.approver_2]))
        self.approver_2.action_archive()

        request = self._prepare_request(category)

        self.assertEqual(request.approver_ids.user_id, self.approver_1)

    def test_archived_members_do_not_staff_a_steps_minimum(self):
        category = self._category(listed_step([self.approver_1, self.approver_2], 2))
        self.approver_2.action_archive()
        request = self._prepare_request(category, confirm=False)

        with self.assertRaises(UserError):
            request.action_confirm()

    def test_archiving_a_delegate_hands_the_row_back_to_its_approver(self):
        category = self._category(listed_step([self.approver_1]))
        request = self._prepare_request(category)
        row = request.approver_ids
        self._delegate_row(row, self.delegate_user)

        self.delegate_user.action_archive()

        self.assertFalse(row.delegate_id)
        self.assertEqual(row._get_effective_approver(), self.approver_1)
        request.with_user(self.approver_1).action_approve()
        self.assertEqual(request.state, "approved")

    def test_the_successor_of_an_archived_approver_is_asked(self):
        category = self._category(
            listed_step([self.approver_1, self.approver_2]),
            escalate_overdue=True,
            escalation_user_id=self.successor.id,
        )
        request = self._prepare_request(category)

        self.approver_1.action_archive()

        self.assertEqual(self._row(request, self.successor).state, "pending")
        self.assertTrue(request._get_approval_activities(user=self.successor))
        self.assertFalse(request._get_approval_activities(user=self.approver_1))

    def test_a_step_cannot_stop_counting_the_only_approvers_it_had(self):
        category = self._category(pool_step([]))
        step = category.step_ids
        self.assertTrue(step.counts_added_approvers)

        with self.assertRaises(ValidationError):
            step.write({"counts_added_approvers": False})

    def test_a_live_reroute_asking_a_current_delegate_ends_their_delegation(self):
        category = self._category(
            listed_step([self.approver_1], name="Main", sequence=10)
            + listed_step(
                [self.delegate_user],
                name="Urgent",
                sequence=20,
                condition_field="priority",
                operator="gte",
                threshold=3,
            )
        )
        request = self._prepare_request(category, priority="1")
        row = self._row(request, self.approver_1)
        self._delegate_row(row, self.delegate_user)

        request.with_user(self.owner_user).write({"priority": "3"})

        self.assertTrue(self._row(request, self.delegate_user))
        self.assertFalse(row.delegate_id)

    def test_a_delegation_outside_its_window_gives_no_reach(self):
        category = self._category(listed_step([self.approver_1]))
        request = self._prepare_request(category)
        row = self._row(request, self.approver_1)
        today = date.today()
        for start, end in (
            (today - timedelta(days=5), today - timedelta(days=2)),
            (today + timedelta(days=2), today + timedelta(days=5)),
        ):
            row.write(
                {
                    "delegate_id": self.delegate_user.id,
                    "delegate_start_date": start,
                    "delegate_end_date": end,
                }
            )
            self.assertNotIn(self.delegate_user, request.pending_user_ids)
        self._delegate_row(row, self.delegate_user)
        self.assertIn(self.delegate_user, request.pending_user_ids)
