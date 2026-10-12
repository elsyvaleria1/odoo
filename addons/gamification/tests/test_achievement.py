from unittest.mock import patch

from odoo.tests import Form, common

from odoo.addons.mail.tests.common import mail_new_test_user


class TestAchievement(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        patch_email = patch(
            "odoo.addons.mail.models.mail_template.MailTemplate.send_mail",
            lambda *args, **kwargs: None,
        )
        cls.startClassPatcher(patch_email)

        cls.user_1 = mail_new_test_user(
            cls.env,
            login="ach_user1",
            name="Achievement User 1",
            email="ach1@example.com",
            karma=0,
            groups="base.group_user,base.group_partner_manager",
        )
        cls.user_2 = mail_new_test_user(
            cls.env,
            login="ach_user2",
            name="Achievement User 2",
            email="ach2@example.com",
            karma=0,
            groups="base.group_user,base.group_partner_manager",
        )

        cls.badge = cls.env["gamification.badge"].create(
            {
                "name": "Achievement Test Badge",
                "rule_auth": "nobody",
            }
        )

        cls.partner_model = cls.env["ir.model"]._get("res.partner")

        cls.achievement = cls.env["gamification.achievement"].create(
            {
                "name": "First Contact",
                "description": "Create your first partner record.",
                "hint": "Try creating a contact...",
                "model_id": cls.partner_model.id,
                "trigger_domain": "[('create_uid', '=', user.id), ('name', 'ilike', 'Achievement Test')]",
                "trigger_count": 1,
                "badge_id": cls.badge.id,
                "karma_reward": 50,
                "rarity": "common",
                "hidden": True,
            }
        )

    def test_achievement_form_resolves_its_domain_model(self):
        self.assertEqual(self.achievement.model_name, "res.partner")
        form = Form(self.env["gamification.achievement"])
        self.assertFalse(form.model_name)
        form.model_id = self.partner_model
        self.assertEqual(form.model_name, "res.partner")

    def test_check_achievement_no_matching_records(self):
        unlocks = self.achievement._check_achievement_for_users(self.user_1)
        self.assertFalse(unlocks, "Should not unlock without matching records")

    def test_check_achievement_unlock_on_match(self):
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Achievement Test Partner",
            }
        )

        unlocks = self.achievement._check_achievement_for_users(self.user_1)

        self.assertEqual(len(unlocks), 1)
        self.assertEqual(unlocks.user_id, self.user_1)
        self.assertEqual(unlocks.achievement_id, self.achievement)

    def test_unlock_uniqueness(self):
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Achievement Test Partner",
            }
        )

        unlocks_1 = self.achievement._check_achievement_for_users(self.user_1)
        self.assertEqual(len(unlocks_1), 1)

        unlocks_2 = self.achievement._check_achievement_for_users(self.user_1)
        self.assertFalse(unlocks_2, "Should not re-unlock already unlocked achievement")

        total = self.env["gamification.achievement.unlock"].search_count(
            [
                ("achievement_id", "=", self.achievement.id),
                ("user_id", "=", self.user_1.id),
            ]
        )
        self.assertEqual(total, 1)

    def test_grant_rewards_karma(self):
        initial_karma = self.user_1.karma
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Achievement Test Partner",
            }
        )

        unlocks = self.achievement._check_achievement_for_users(self.user_1)
        unlocks._grant_rewards()

        self.assertEqual(
            self.user_1.karma,
            initial_karma + self.achievement.karma_reward,
            "Should grant karma reward on unlock",
        )

    def test_grant_rewards_badge(self):
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Achievement Test Partner",
            }
        )

        unlocks = self.achievement._check_achievement_for_users(self.user_1)
        unlocks._grant_rewards()

        badge_users = self.env["gamification.badge.user"].search(
            [
                ("user_id", "=", self.user_1.id),
                ("badge_id", "=", self.badge.id),
            ]
        )
        self.assertEqual(
            len(badge_users), 1, "Should grant badge on achievement unlock"
        )

    def test_no_rewards_when_no_karma_or_badge(self):
        achievement_no_reward = self.env["gamification.achievement"].create(
            {
                "name": "No Reward Achievement",
                "model_id": self.partner_model.id,
                "trigger_domain": "[('create_uid', '=', user.id), ('name', 'ilike', 'NoReward Test')]",
                "trigger_count": 1,
                "karma_reward": 0,
                "rarity": "rare",
            }
        )
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "NoReward Test Partner",
            }
        )
        initial_karma = self.user_1.karma

        unlocks = achievement_no_reward._check_achievement_for_users(self.user_1)
        unlocks._grant_rewards()

        self.assertEqual(self.user_1.karma, initial_karma)

    def test_trigger_count_threshold(self):
        achievement_3 = self.env["gamification.achievement"].create(
            {
                "name": "Three Contacts",
                "model_id": self.partner_model.id,
                "trigger_domain": "[('create_uid', '=', user.id), ('name', 'ilike', 'Threshold Test')]",
                "trigger_count": 3,
                "karma_reward": 25,
                "rarity": "epic",
            }
        )

        for i in range(2):
            self.env["res.partner"].with_user(self.user_1).create(
                {
                    "name": f"Threshold Test Partner {i}",
                }
            )

        unlocks = achievement_3._check_achievement_for_users(self.user_1)
        self.assertFalse(unlocks, "Should not unlock with only 2 of 3 required records")

        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Threshold Test Partner 3",
            }
        )

        unlocks = achievement_3._check_achievement_for_users(self.user_1)
        self.assertEqual(len(unlocks), 1, "Should unlock with 3 matching records")

    def test_multi_user_check(self):
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Achievement Test Partner",
            }
        )

        unlocks = self.achievement._check_achievement_for_users(
            self.user_1 | self.user_2
        )

        self.assertEqual(len(unlocks), 1)
        self.assertEqual(unlocks.user_id, self.user_1)

    def test_cron_check_achievements(self):
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Achievement Test Partner",
            }
        )
        initial_karma = self.user_1.karma

        self.env["gamification.achievement"]._cron_check_achievements()

        self.assertEqual(
            self.user_1.karma,
            initial_karma + self.achievement.karma_reward,
            "Cron should trigger achievement check and grant rewards",
        )

    def test_unlock_count_computed(self):
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Achievement Test Partner",
            }
        )
        self.env["res.partner"].with_user(self.user_2).create(
            {
                "name": "Achievement Test Partner 2",
            }
        )

        unlocks = self.achievement._check_achievement_for_users(
            self.user_1 | self.user_2
        )
        self.assertEqual(len(unlocks), 2)

        self.achievement.invalidate_recordset(["unlock_count"])
        self.assertEqual(self.achievement.unlock_count, 2)

    def test_inactive_achievement_skipped_by_cron(self):
        self.achievement.active = False
        self.env["res.partner"].with_user(self.user_1).create(
            {
                "name": "Achievement Test Partner",
            }
        )

        self.env["gamification.achievement"]._cron_check_achievements()

        unlocks = self.env["gamification.achievement.unlock"].search(
            [
                ("achievement_id", "=", self.achievement.id),
            ]
        )
        self.assertFalse(unlocks, "Inactive achievement should not be checked by cron")

    def test_trigger_domain_not_referencing_user_is_accepted_as_shared(self):
        achievement = self.env["gamification.achievement"].create(
            {
                "name": "Global Trigger Achievement",
                "model_id": self.partner_model.id,
                "trigger_domain": "[('active', '=', True)]",
                "trigger_count": 1,
            }
        )
        self.assertTrue(achievement)
        self.assertIn(
            "unlocks",
            self.env["gamification.achievement"]._fields["trigger_domain"].help,
            "the trigger_domain field must document the shared-query "
            "caveat for a domain that never references 'user'",
        )

    def test_trigger_domain_referencing_user_is_accepted(self):
        achievement = self.env["gamification.achievement"].create(
            {
                "name": "Per-User Trigger Achievement",
                "model_id": self.partner_model.id,
                "trigger_domain": "[('create_uid', '=', user.id)]",
                "trigger_count": 1,
            }
        )
        self.assertTrue(achievement)
