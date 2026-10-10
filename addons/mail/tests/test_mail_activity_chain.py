from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestChainedActivity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.next_owner = new_test_user(cls.env, login="next_owner")
        cls.writer = new_test_user(
            cls.env, login="writer", groups="base.group_user,base.group_partner_manager"
        )
        cls.reader = new_test_user(cls.env, login="reader", groups="base.group_user")
        ActivityType = cls.env["mail.activity.type"]
        cls.next_type = ActivityType.create(
            {"name": "Probe: follow up", "default_user_id": cls.next_owner.id}
        )
        cls.first_type = ActivityType.create(
            {
                "name": "Probe: call",
                "chaining_type": "trigger",
                "triggered_next_type_id": cls.next_type.id,
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Chained partner"})

    def activity_for(self, user):
        return self.env["mail.activity"].create(
            {
                "activity_type_id": self.first_type.id,
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.partner.id,
                "user_id": user.id,
            }
        )

    def test_the_successor_is_created_on_the_completers_authority(self):
        self.activity_for(self.writer).with_user(self.writer).action_feedback("done")
        successor = self.env["mail.activity"].search(
            [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", self.partner.id),
                ("activity_type_id", "=", self.next_type.id),
            ]
        )
        self.assertEqual(successor.user_id, self.next_owner)
        self.assertEqual(successor.create_uid, self.writer)
        self.assertEqual(successor.previous_activity_type_id, self.first_type)

    def test_a_completer_who_may_not_post_on_the_record_finishes_without_successor(
        self,
    ):
        activity = self.activity_for(self.reader)
        activity.with_user(self.reader).action_feedback("done")
        self.assertFalse(activity.active, "finishing one's own work always succeeds")
        self.assertFalse(
            self.env["mail.activity"].search(
                [
                    ("res_model", "=", "res.partner"),
                    ("res_id", "=", self.partner.id),
                    ("activity_type_id", "=", self.next_type.id),
                ]
            )
        )
        skipped = self.env["ir.access.log"].search(
            [("event", "=", "activity_successor_skipped")]
        )
        self.assertEqual(skipped.subject_user_id, self.next_owner)
        self.assertEqual(skipped.actor_id, self.reader)
        self.assertEqual(skipped.reason, self.next_type.name)
        self.assertEqual(skipped.res_ids, str(self.partner.id))


@tagged("post_install", "-at_install")
class TestSuccessorAssignee(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.assignee = new_test_user(
            cls.env, login="assignee", groups="base.group_user"
        )
        cls.manager = new_test_user(
            cls.env,
            login="manager",
            groups="base.group_user,base.group_partner_manager",
        )
        ActivityType = cls.env["mail.activity.type"]
        cls.next_type = ActivityType.create({"name": "Probe: unassigned next"})
        cls.first_type = ActivityType.create(
            {
                "name": "Probe: first",
                "chaining_type": "trigger",
                "triggered_next_type_id": cls.next_type.id,
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Chained partner"})

    def test_the_successor_stays_with_the_assignee_when_someone_else_completes(self):
        activity = self.env["mail.activity"].create(
            {
                "activity_type_id": self.first_type.id,
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.partner.id,
                "user_id": self.assignee.id,
            }
        )
        activity.with_user(self.manager).action_feedback("done for them")
        successor = self.env["mail.activity"].search(
            [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", self.partner.id),
                ("activity_type_id", "=", self.next_type.id),
            ]
        )
        self.assertEqual(successor.user_id, self.assignee)

    def test_picking_a_type_on_the_form_keeps_the_chosen_assignee(self):
        activity = self.env["mail.activity"].new({"user_id": self.assignee.id})
        activity.activity_type_id = self.next_type
        activity._onchange_activity_type_id()
        self.assertEqual(activity.user_id, self.assignee)
