from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time
from psycopg.errors import UniqueViolation

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, common

from odoo.addons.mail.tests.common import mail_new_test_user


class TestStreakCommon(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        patch_email = patch(
            "odoo.addons.mail.models.mail_template.MailTemplate.send_mail",
            lambda *args, **kwargs: None,
        )
        cls.startClassPatcher(patch_email)

        cls.test_user = mail_new_test_user(
            cls.env,
            login="streak_user",
            name="Streak User",
            email="streak@example.com",
            karma=0,
            groups="base.group_user",
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.date_field = cls.env["ir.model.fields"].search(
            [("model", "=", "res.partner"), ("name", "=", "write_date")],
            limit=1,
        )

        cls.streak_type = cls.env["gamification.streak.type"].create(
            {
                "name": "Daily Partner Update",
                "model_id": cls.partner_model.id,
                "date_field_id": cls.date_field.id,
                "domain": "[('create_uid', '=', user.id)]",
                "karma_bonus": 10,
                "freeze_allowance": 2,
            }
        )


class TestStreak(TestStreakCommon):
    def setUp(self):
        super().setUp()
        self.env["gamification.streak"].search(
            [
                ("user_id", "=", self.test_user.id),
            ]
        ).unlink()

    def test_streak_type_form_resolves_its_domain_model(self):
        self.assertEqual(self.streak_type.model_name, "res.partner")
        form = Form(self.env["gamification.streak.type"])
        self.assertFalse(form.model_name)
        form.model_id = self.partner_model
        self.assertEqual(form.model_name, "res.partner")

    def test_get_user_streaks_creates_missing(self):
        Streak = self.env["gamification.streak"]
        Streak.search([("user_id", "=", self.test_user.id)]).unlink()

        Streak._get_or_create_user_streaks(self.test_user)

        streaks = Streak.search([("user_id", "=", self.test_user.id)])
        active_types = self.env["gamification.streak.type"].search(
            [("active", "=", True)]
        )
        self.assertEqual(
            len(streaks),
            len(active_types),
            "Should create one streak per active type",
        )

    def test_get_user_streaks_idempotent(self):
        Streak = self.env["gamification.streak"]
        Streak.search([("user_id", "=", self.test_user.id)]).unlink()

        Streak._get_or_create_user_streaks(self.test_user)
        count_1 = Streak.search_count([("user_id", "=", self.test_user.id)])

        Streak._get_or_create_user_streaks(self.test_user)
        count_2 = Streak.search_count([("user_id", "=", self.test_user.id)])

        self.assertEqual(count_1, count_2, "Second call should not create duplicates")

    def test_record_activity_increments_count(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        self.assertEqual(streak.current_count, 0)

        streak._record_activity()

        self.assertEqual(streak.current_count, 1)
        self.assertEqual(streak.last_activity_date, fields.Date.today())
        self.assertEqual(streak.longest_count, 1)

    def test_record_activity_idempotent_same_day(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        streak._record_activity()
        streak._record_activity()

        self.assertEqual(streak.current_count, 1, "Should not count same day twice")

    def test_record_activity_rejects_mixed_streak_types_for_one_user(self):
        other_streak_type = self.env["gamification.streak.type"].create(
            {
                "name": "Other Streak Type",
                "model_id": self.partner_model.id,
                "date_field_id": self.date_field.id,
                "domain": "[('create_uid', '=', user.id)]",
                "karma_bonus": 5,
                "freeze_allowance": 2,
            }
        )
        streak_a = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        streak_b = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": other_streak_type.id,
                "freeze_remaining": other_streak_type.freeze_allowance,
            }
        )
        with self.assertRaises(UserError):
            (streak_a | streak_b)._record_activity()

    def test_record_activity_grants_karma(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        initial_karma = self.test_user.karma

        streak._record_activity()

        self.assertEqual(
            self.test_user.karma,
            initial_karma + self.streak_type.karma_bonus,
        )
        self.assertEqual(streak.total_karma_earned, self.streak_type.karma_bonus)

    def test_milestone_karma_multiplier(self):
        from odoo.addons.gamification.models.gamification_streak import (
            STREAK_MILESTONES,
        )

        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
                "current_count": 6,
                "longest_count": 6,
            }
        )
        streak.env.cr.execute(
            "UPDATE gamification_streak SET current_count = 6, longest_count = 6 WHERE id = %s",
            [streak.id],
        )
        streak.invalidate_recordset()
        initial_karma = self.test_user.karma

        with freeze_time("2026-04-01"):
            streak._record_activity()

        expected_multiplier = STREAK_MILESTONES[7]
        expected_karma = self.streak_type.karma_bonus * expected_multiplier
        self.assertEqual(
            self.test_user.karma,
            initial_karma + expected_karma,
            f"Day 7 milestone should grant {expected_multiplier}x karma",
        )

    def test_break_streak_resets_count(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        streak.env.cr.execute(
            "UPDATE gamification_streak SET current_count = 5, longest_count = 5 WHERE id = %s",
            [streak.id],
        )
        streak.invalidate_recordset()

        streak._break_streak()

        self.assertEqual(streak.current_count, 0)
        self.assertEqual(streak.state, "broken")
        self.assertEqual(streak.longest_count, 5, "Longest should be preserved")

    def test_record_activity_revives_broken_streak(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        streak._break_streak()
        self.assertEqual(streak.state, "broken")

        streak._record_activity()

        self.assertEqual(streak.state, "active")
        self.assertEqual(streak.current_count, 1)

    @freeze_time("2026-03-15")
    def test_cron_freeze_day_used(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": 2,
            }
        )
        streak.env.cr.execute(
            "UPDATE gamification_streak SET current_count = 3, last_activity_date = %s WHERE id = %s",
            [date.today() - timedelta(days=2), streak.id],
        )
        streak.invalidate_recordset()

        with patch.object(
            type(self.streak_type),
            "_check_user_activity_batch",
            side_effect=lambda users, check_date: set(),
        ):
            self.env["gamification.streak"]._cron_update_streaks()

        streak.invalidate_recordset()
        self.assertEqual(streak.state, "active", "Should still be active after freeze")
        self.assertEqual(streak.freeze_remaining, 1, "One freeze day should be used")

    @freeze_time("2026-03-15")
    def test_cron_breaks_streak_no_freeze(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": 0,
            }
        )
        streak.env.cr.execute(
            "UPDATE gamification_streak SET current_count = 3, last_activity_date = %s WHERE id = %s",
            [date.today() - timedelta(days=2), streak.id],
        )
        streak.invalidate_recordset()

        with patch.object(
            type(self.streak_type),
            "_check_user_activity_batch",
            side_effect=lambda users, check_date: set(),
        ):
            self.env["gamification.streak"]._cron_update_streaks()

        streak.invalidate_recordset()
        self.assertEqual(streak.state, "broken")
        self.assertEqual(streak.current_count, 0)

    @freeze_time("2026-03-15")
    def test_cron_records_activity_when_found(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": 2,
            }
        )
        streak.env.cr.execute(
            "UPDATE gamification_streak SET current_count = 3, last_activity_date = %s WHERE id = %s",
            [date.today() - timedelta(days=2), streak.id],
        )
        streak.invalidate_recordset()

        with patch.object(
            type(self.streak_type),
            "_check_user_activity_batch",
            side_effect=lambda users, check_date: set(users.ids),
        ):
            self.env["gamification.streak"]._cron_update_streaks()

        streak.invalidate_recordset()
        self.assertEqual(streak.state, "active")
        self.assertEqual(streak.current_count, 4)

    @freeze_time("2026-04-01")
    def test_cron_resets_freeze_on_first_of_month(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": 0,
            }
        )
        streak.env.cr.execute(
            "UPDATE gamification_streak SET last_activity_date = %s WHERE id = %s",
            [date(2026, 3, 31), streak.id],
        )
        streak.invalidate_recordset()

        with patch.object(
            type(self.streak_type),
            "_check_user_activity_batch",
            side_effect=lambda users, check_date: set(users.ids),
        ):
            self.env["gamification.streak"]._cron_update_streaks()

        streak.invalidate_recordset()
        self.assertEqual(
            streak.freeze_remaining,
            self.streak_type.freeze_allowance,
            "Freeze should be reset on 1st of month",
        )

    def test_unique_constraint_user_streak_type(self):
        self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        with self.assertRaises(UniqueViolation):
            self.env["gamification.streak"].create(
                {
                    "user_id": self.test_user.id,
                    "streak_type_id": self.streak_type.id,
                    "freeze_remaining": self.streak_type.freeze_allowance,
                }
            )

    def test_streak_type_user_count(self):
        user2 = mail_new_test_user(
            self.env,
            login="streak_user2",
            name="Streak User 2",
            email="streak2@example.com",
            karma=0,
            groups="base.group_user",
        )
        self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        s2 = self.env["gamification.streak"].create(
            {
                "user_id": user2.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        self.streak_type.invalidate_recordset(["user_count"])
        self.assertEqual(self.streak_type.user_count, 2)

        s2._break_streak()
        self.streak_type.invalidate_recordset(["user_count"])
        self.assertEqual(
            self.streak_type.user_count, 1, "Broken streaks should not count"
        )

    def test_get_user_streaks_as_employee(self):
        Streak = self.env["gamification.streak"]
        Streak.search([("user_id", "=", self.test_user.id)]).unlink()

        Streak.with_user(self.test_user)._get_or_create_user_streaks(self.test_user)

        streaks = Streak.search([("user_id", "=", self.test_user.id)])
        active_types = self.env["gamification.streak.type"].search(
            [("active", "=", True)]
        )
        self.assertEqual(
            len(streaks),
            len(active_types),
            "Employee should be able to create streaks via _get_or_create_user_streaks",
        )

    @freeze_time("2026-03-15")
    def test_cron_revives_broken_streak_on_activity(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": 0,
            }
        )
        streak._break_streak()
        self.assertEqual(streak.state, "broken")
        self.assertEqual(streak.current_count, 0)

        with patch.object(
            type(self.streak_type),
            "_check_user_activity_batch",
            side_effect=lambda users, check_date: set(users.ids),
        ):
            self.env["gamification.streak"]._cron_update_streaks()

        streak.invalidate_recordset()
        self.assertEqual(
            streak.state, "active", "Broken streak should revive on activity"
        )
        self.assertEqual(streak.current_count, 1)

    @freeze_time("2026-04-01")
    def test_cron_revival_gets_this_months_freeze_reset(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": 0,
            }
        )
        streak._break_streak()
        self.assertEqual(streak.state, "broken")

        with patch.object(
            type(self.streak_type),
            "_check_user_activity_batch",
            side_effect=lambda users, check_date: set(users.ids),
        ):
            self.env["gamification.streak"]._cron_update_streaks()

        streak.invalidate_recordset()
        self.assertEqual(
            streak.state, "active", "Broken streak should revive on activity"
        )
        self.assertEqual(
            streak.freeze_remaining,
            self.streak_type.freeze_allowance,
            "A streak revived on the 1st of the month should still receive "
            "that month's freeze allowance",
        )

    @freeze_time("2026-03-15")
    def test_cron_does_not_rebreak_broken_streak(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": 2,
            }
        )
        streak._break_streak()
        self.assertEqual(streak.state, "broken")

        with patch.object(
            type(self.streak_type),
            "_check_user_activity_batch",
            side_effect=lambda users, check_date: set(),
        ):
            self.env["gamification.streak"]._cron_update_streaks()

        streak.invalidate_recordset()
        self.assertEqual(streak.state, "broken")
        self.assertEqual(
            streak.freeze_remaining,
            2,
            "Freeze days should not be consumed on broken streaks",
        )

    def test_display_name(self):
        streak = self.env["gamification.streak"].create(
            {
                "user_id": self.test_user.id,
                "streak_type_id": self.streak_type.id,
                "freeze_remaining": self.streak_type.freeze_allowance,
            }
        )
        self.assertIn("0 days", streak.display_name)
        self.assertIn(self.streak_type.name, streak.display_name)

    def test_domain_not_referencing_user_is_accepted_as_a_shared_streak(self):
        streak_type = self.env["gamification.streak.type"].create(
            {
                "name": "Global Domain Streak",
                "model_id": self.partner_model.id,
                "date_field_id": self.date_field.id,
                "domain": "[('active', '=', True)]",
            }
        )
        self.assertTrue(streak_type)
        self.assertIn(
            "credited",
            self.env["gamification.streak.type"]._fields["domain"].help,
            "the domain field must document the shared-query caveat for a "
            "domain that never references 'user'",
        )

    def test_domain_referencing_user_is_accepted(self):
        streak_type = self.env["gamification.streak.type"].create(
            {
                "name": "Per-User Domain Streak",
                "model_id": self.partner_model.id,
                "date_field_id": self.date_field.id,
                "domain": "[('create_uid', '=', user.id)]",
            }
        )
        self.assertTrue(streak_type)
