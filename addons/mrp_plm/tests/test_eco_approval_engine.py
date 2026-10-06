from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .test_common import TestPlmCommon


@tagged("post_install", "-at_install")
class TestEcoApprovalEngine(TestPlmCommon):
    """An engineering change's stage approvals are approval requests.

    A stage's role templates are steps of the Engineering Change category; a mandatory
    role blocks, an optional or comment role advises. Entering a stage raises that
    stage's request (mixin.approval.subjects, key stage:<id>), and the ECO's kanban
    state, stage gating and Approve / Reject follow it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mandatory_user = new_test_user(
            cls.env, "eco_mandatory", "mrp_plm.group_plm_user"
        )
        cls.optional_user = new_test_user(
            cls.env, "eco_optional", "mrp_plm.group_plm_user"
        )
        cls.comment_user = new_test_user(
            cls.env, "eco_comment", "mrp_plm.group_plm_user"
        )
        cls.flow_type = cls.env["mrp.eco.type"].create({"name": "Engine ECO type"})
        cls.new_stage = cls.env["mrp.eco.stage"].create(
            {
                "name": "Engine New",
                "sequence": 0,
                "type_ids": [Command.link(cls.flow_type.id)],
            }
        )
        cls.review_stage = cls.env["mrp.eco.stage"].create(
            {
                "name": "Engine Review",
                "sequence": 10,
                "type_ids": [Command.link(cls.flow_type.id)],
                "approval_template_ids": [
                    Command.create(
                        {
                            "name": "Engineering",
                            "approval_type": "mandatory",
                            "user_ids": [Command.set(cls.mandatory_user.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "name": "Quality",
                            "approval_type": "optional",
                            "user_ids": [Command.set(cls.optional_user.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "name": "Finance",
                            "approval_type": "comment",
                            "user_ids": [Command.set(cls.comment_user.ids)],
                        }
                    ),
                ],
            }
        )
        cls.done_stage = cls.env["mrp.eco.stage"].create(
            {
                "name": "Engine Done",
                "sequence": 30,
                "type_ids": [Command.link(cls.flow_type.id)],
                "final_stage": True,
            }
        )
        cls.mandatory, cls.optional, cls.comment = (
            cls.review_stage.approval_template_ids.sorted("id")
        )

    def _eco_in_review(self):
        eco = self._create_eco(
            "Engine ECO", self.bom_table, self.flow_type.id, self.new_stage.id
        )
        eco.stage_id = self.review_stage
        return eco

    def _request(self, eco):
        return eco.sudo()._get_stage_request()

    def _row(self, request, user):
        return request.approver_ids.filtered(lambda row: row.user_id == user)

    def test_each_role_is_a_step_of_the_engineering_change_category(self):
        category = self.env.ref("mrp_plm.approval_category_eco")
        self.assertEqual(self.mandatory.step_id.category_id, category)
        self.assertFalse(self.mandatory.step_id.advisory)
        self.assertTrue(self.optional.step_id.advisory)
        self.assertTrue(self.comment.step_id.advisory)

        other = new_test_user(self.env, "eco_other_engineer", "mrp_plm.group_plm_user")
        self.mandatory.user_ids = [Command.set(other.ids)]
        self.assertEqual(self.mandatory.step_id.user_ids, other)

        step = self.optional.step_id
        self.optional.unlink()
        self.assertFalse(step.exists())

    def test_deleting_several_roles_at_once_takes_every_step_with_them(self):
        """The steps are collected before the templates go and unlinked after.

        A relational read's prefetch set is lazy over the records it was read
        from, so a set captured here is worth capturing as a set: `exists()`
        answers for the whole of it in one query, where a per-record `exists()`
        inside a `filtered` asks once per step.
        """
        steps = (self.mandatory | self.comment).step_id
        self.assertEqual(len(steps), 2)

        (self.mandatory | self.comment).unlink()

        self.assertFalse(
            steps.exists(), "both approval steps must go with their templates"
        )
        self.assertTrue(
            self.optional.step_id.exists(),
            "the role that was not deleted must keep its step",
        )

    def test_entering_a_stage_asks_every_role(self):
        eco = self._eco_in_review()

        request = self._request(eco)
        self.assertEqual(request.state, "pending")
        self.assertEqual(
            request.approver_ids.user_id,
            self.mandatory_user | self.optional_user | self.comment_user,
        )
        self.assertEqual(
            eco.sudo().activity_ids.user_id,
            self.mandatory_user | self.optional_user | self.comment_user,
        )
        self.assertEqual(eco.kanban_state, "normal")
        self.assertFalse(eco.allow_change_stage)

    def test_the_mandatory_approval_readies_the_change(self):
        eco = self._eco_in_review()

        eco.with_user(self.mandatory_user).approve()

        request = self._request(eco)
        self.assertEqual(request.state, "approved")
        self.assertEqual(self._row(request, self.optional_user).state, "waiting")
        self.assertEqual(eco.kanban_state, "done")
        self.assertTrue(eco.allow_change_stage)

    def test_an_optional_rejection_is_advice(self):
        eco = self._eco_in_review()

        eco.with_user(self.optional_user).reject()

        request = self._request(eco)
        self.assertEqual(request.state, "pending")
        self.assertEqual(self._row(request, self.optional_user).state, "refused")
        self.assertEqual(eco.kanban_state, "normal")
        eco.with_user(self.mandatory_user).approve()
        self.assertEqual(eco.kanban_state, "done")

    def test_a_mandatory_rejection_blocks_the_change(self):
        eco = self._eco_in_review()

        eco.with_user(self.mandatory_user).reject()

        self.assertEqual(self._request(eco).state, "refused")
        self.assertEqual(eco.kanban_state, "blocked")
        with self.assertRaises(UserError):
            eco.stage_id = self.done_stage

    def test_an_approver_changing_their_mind_keeps_the_others_decisions(self):
        eco = self._eco_in_review()
        eco.with_user(self.optional_user).approve()
        eco.with_user(self.mandatory_user).reject()
        refused = self._request(eco)
        self.assertEqual(refused.state, "refused")
        self.assertTrue(eco.with_user(self.mandatory_user).user_can_approve)

        eco.with_user(self.mandatory_user).approve()

        request = self._request(eco)
        self.assertNotEqual(request, refused)
        self.assertEqual(request.state, "approved")
        self.assertEqual(self._row(request, self.optional_user).state, "approved")
        self.assertEqual(
            self._row(request, self.optional_user).decided_by_user_id,
            self.optional_user,
        )
        self.assertEqual(refused.state, "refused")
        self.assertEqual(eco.kanban_state, "done")

    def test_a_comment_from_a_comment_role_records_its_advice(self):
        eco = self._eco_in_review()

        eco.with_user(self.comment_user).message_post(
            body="No objection", message_type="comment"
        )

        request = self._request(eco)
        self.assertEqual(self._row(request, self.comment_user).state, "approved")
        self.assertEqual(request.state, "pending")

    def test_a_batch_comment_from_a_comment_role_records_its_advice(self):
        ecos = self._eco_in_review() | self._eco_in_review()

        ecos.with_user(self.comment_user)._message_post_values_all(
            {
                eco.id: {"body": "No objection", "message_type": "comment"}
                for eco in ecos
            }
        )

        for eco in ecos:
            request = self._request(eco)
            self.assertEqual(self._row(request, self.comment_user).state, "approved")

    def test_leaving_a_stage_cancels_its_undecided_request(self):
        eco = self._eco_in_review()
        request = self._request(eco)

        eco.stage_id = self.new_stage

        self.assertEqual(request.state, "cancelled")
        self.assertFalse(
            eco.sudo()._get_live_approval_request(f"stage:{self.review_stage.id}")
        )

    def test_who_can_approve_or_reject(self):
        eco = self._eco_in_review()

        self.assertTrue(eco.with_user(self.mandatory_user).user_can_approve)
        self.assertTrue(eco.with_user(self.optional_user).user_can_reject)
        self.assertFalse(eco.with_user(self.comment_user).user_can_approve)
        self.assertTrue(eco.with_user(self.mandatory_user).awaiting_my_validation)
        eco.with_user(self.mandatory_user).approve()
        self.assertFalse(eco.with_user(self.mandatory_user).user_can_approve)
        self.assertFalse(eco.with_user(self.mandatory_user).awaiting_my_validation)
