from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAccessReviewActivities(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login="review_admin", groups="base.group_erp_manager"
        )
        cls.alice = new_test_user(
            cls.env, login="review_alice", groups="base.group_user"
        )
        cls.bob = new_test_user(cls.env, login="review_bob", groups="base.group_user")
        cls.group = cls.env["res.groups"].create({"name": "Probe: reviewed desk"})
        cls.holders = cls.env["res.users"]
        for login in ("review_carol", "review_dan"):
            holder = new_test_user(cls.env, login=login, groups="base.group_user")
            holder.group_ids = [Command.link(cls.group.id)]
            cls.holders |= holder

    def start(self):
        campaign = (
            self.env["access.review.campaign"]
            .with_user(self.admin)
            .create(
                {
                    "name": "Probe desk review",
                    "kind": "memberships",
                    "group_ids": [Command.set(self.group.ids)],
                    "reviewer": "named",
                    "reviewer_ids": [
                        Command.set([self.admin.id, self.alice.id, self.bob.id])
                    ],
                }
            )
        )
        campaign.action_start()
        return campaign

    def todo(self, items, user):
        return self.env["mail.activity"].search(
            [
                ("res_model", "=", "access.review.item"),
                ("res_id", "in", items.ids),
                ("user_id", "=", user.id),
                (
                    "activity_type_id",
                    "=",
                    self.env.ref("mail.mail_activity_data_todo").id,
                ),
            ]
        )

    def test_a_reviewer_who_is_no_administrator_is_asked_each_item(self):
        campaign = self.start()
        items = campaign.item_ids
        self.assertEqual(items.subject_user_id, self.holders)
        for reviewer in (self.alice, self.bob):
            activities = self.todo(items, reviewer)
            self.assertEqual(sorted(activities.mapped("res_id")), sorted(items.ids))
            self.assertEqual(
                set(activities.mapped("date_deadline")), {campaign.date_deadline}
            )
            self.assertIn(campaign.name, activities[0].summary)
            self.assertEqual(
                self.env["access.review.item"]
                .with_user(reviewer)
                .search([("id", "in", items.ids)]),
                items,
                "the activity points at an item the reviewer reads",
            )
        self.assertFalse(self.todo(items, self.admin), "the admin has the menu")

    def test_a_decision_clears_the_items_activities_for_every_reviewer(self):
        campaign = self.start()
        decided, other = campaign.item_ids
        decided.with_user(self.alice).action_certify()
        for reviewer in (self.alice, self.bob):
            self.assertFalse(self.todo(decided, reviewer))
            self.assertTrue(self.todo(other, reviewer))

    def test_a_revocation_at_the_deadline_clears_them_too(self):
        campaign = self.start()
        campaign.on_deadline = "revoke"
        campaign.with_user(self.admin).action_close()
        self.assertFalse(self.todo(campaign.item_ids, self.alice))
        self.assertEqual(set(campaign.item_ids.mapped("decision")), {"revoked"})
