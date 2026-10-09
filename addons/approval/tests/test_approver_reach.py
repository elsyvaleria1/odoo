from datetime import date, timedelta

from odoo.tests import new_test_user, tagged

from .common import ApprovalCommon


@tagged("post_install", "-at_install")
class TestApproverReach(ApprovalCommon):
    def _decider_grants(self, user):
        return self.env["res.users.grant"].search(
            [
                ("user_id", "=", user.id),
                ("group_id", "=", self.env.ref("approval.group_approval_decider").id),
                ("state", "=", "active"),
            ]
        )

    def test_a_step_member_holds_the_decider_group_while_a_member(self):
        person = new_test_user(self.env, login="reach_asked", groups="base.group_user")
        category = self._make_category(name="Reach Grant", approvers=[person])
        self.env.cr.flush()
        self.assertTrue(person.has_group("approval.group_approval_decider"))
        self.assertFalse(person.has_group("approval.group_approval_approver"))
        grant = self._decider_grants(person)
        self.assertEqual(grant.cause, "approval_step")
        self.assertEqual(grant.cause_res_id, category.step_ids.id)
        request = self._prepare_request(category)
        self.assertIn(person, request.pending_user_ids)
        request.with_user(person).action_approve()
        self.assertFalse(request.pending_user_ids)

        category.step_ids.member_ids.unlink()
        self.env.cr.flush()
        self.assertFalse(self._decider_grants(person))
        self.assertFalse(person.has_group("approval.group_approval_decider"))

    def test_moving_a_delegations_window_moves_the_decider_group(self):
        principal = new_test_user(
            self.env, login="reach_principal", groups="base.group_user"
        )
        stand_in = new_test_user(
            self.env, login="reach_stand_in", groups="base.group_user"
        )
        request = self._prepare_request(
            self._make_category(name="Reach Window", approvers=[principal])
        )
        row = request.approver_ids
        today = date.today()
        row.sudo().write(
            {
                "delegate_id": stand_in.id,
                "delegate_start_date": today + timedelta(days=2),
                "delegate_end_date": today + timedelta(days=5),
            }
        )
        self.env.cr.flush()
        self.assertFalse(self._decider_grants(stand_in))

        row.sudo().write({"delegate_start_date": today})
        self.env.cr.flush()
        self.assertEqual(self._decider_grants(stand_in).cause, "approval_delegation")
        self.assertIn(stand_in, request.pending_user_ids)

    def test_extending_a_membership_gives_the_decider_group_back(self):
        person = new_test_user(
            self.env, login="reach_extended", groups="base.group_user"
        )
        member = self._make_category(
            name="Reach Extended", approvers=[person]
        ).step_ids.member_ids
        self.env.cr.flush()
        self.assertTrue(self._decider_grants(person))

        member.write({"date_end": date.today() - timedelta(days=1)})
        self.env.cr.flush()
        self.assertFalse(self._decider_grants(person))

        member.write({"date_end": date.today() + timedelta(days=7)})
        self.env.cr.flush()
        self.assertTrue(self._decider_grants(person))
