from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import common

from odoo.addons.mail.tests.common import mail_new_test_user


class TestMentorship(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        patch_email = patch(
            "odoo.addons.mail.models.mail_template.MailTemplate.send_mail",
            lambda *args, **kwargs: None,
        )
        cls.startClassPatcher(patch_email)

        cls.mentor = mail_new_test_user(
            cls.env,
            login="mentor_user",
            name="Mentor User",
            email="mentor@example.com",
            karma=500,
            groups="base.group_user",
        )
        cls.mentee = mail_new_test_user(
            cls.env,
            login="mentee_user",
            name="Mentee User",
            email="mentee@example.com",
            karma=50,
            groups="base.group_user",
        )

    def _create_mentorship(self, accept=True, **kwargs):
        vals = {
            "mentor_id": self.mentor.id,
            "mentee_id": self.mentee.id,
            "mentor_karma_per_milestone": 25,
            "mentor_karma_on_completion": 100,
            **kwargs,
        }
        record = self.env["gamification.mentorship"].create(vals)
        if accept:
            record.action_accept()
        return record

    def test_create_mentorship(self):
        m = self._create_mentorship(accept=False)
        self.assertEqual(m.state, "pending")
        self.assertEqual(m.mentor_id, self.mentor)
        self.assertEqual(m.mentee_id, self.mentee)

        m.action_accept()
        self.assertEqual(m.state, "active")

    def test_pending_mentorship_pays_nothing(self):
        m = self._create_mentorship(accept=False)
        before = self.mentor.karma

        self.env["gamification.mentorship"]._on_mentee_rank_up(self.mentee)

        self.assertEqual(m.state, "pending")
        self.assertEqual(m.mentee_milestones_reached, 0)
        self.assertEqual(self.mentor.karma, before)

    def test_the_proposer_cannot_accept_their_own_proposal(self):
        m = (
            self.env["gamification.mentorship"]
            .with_user(self.mentor)
            .create({"mentor_id": self.mentor.id, "mentee_id": self.mentee.id})
        )
        with self.assertRaises(AccessError):
            m.with_user(self.mentor).action_accept()

        m.with_user(self.mentee).action_accept()
        self.assertEqual(m.state, "active")

    def test_declining_cancels_the_pairing(self):
        m = self._create_mentorship(accept=False)
        m.with_user(self.mentee).action_decline()
        self.assertEqual(m.state, "cancelled")

    def test_reciprocal_mentorship_is_refused(self):
        self._create_mentorship()
        with self.assertRaises(ValidationError):
            self.env["gamification.mentorship"].create(
                {"mentor_id": self.mentee.id, "mentee_id": self.mentor.id}
            )

    def test_self_mentoring_prevented(self):
        with self.assertRaises(ValidationError):
            self._create_mentorship(mentee_id=self.mentor.id)

    def test_complete_grants_karma(self):
        m = self._create_mentorship()
        initial_karma = self.mentor.karma

        m.action_complete()

        self.assertEqual(m.state, "completed")
        self.assertTrue(m.end_date)
        self.assertEqual(
            self.mentor.karma,
            initial_karma + m.mentor_karma_on_completion,
        )

    def test_complete_grants_badge(self):
        badge = self.env["gamification.badge"].create(
            {
                "name": "Mentor Badge",
                "rule_auth": "nobody",
            }
        )
        m = self._create_mentorship(completion_badge_id=badge.id)

        m.action_complete()

        for user in (self.mentor, self.mentee):
            badge_users = self.env["gamification.badge.user"].search(
                [
                    ("user_id", "=", user.id),
                    ("badge_id", "=", badge.id),
                ]
            )
            self.assertEqual(
                len(badge_users), 1, f"{user.name} should have completion badge"
            )

    def test_cancel_mentorship(self):
        m = self._create_mentorship()
        m.action_cancel()

        self.assertEqual(m.state, "cancelled")
        self.assertTrue(m.end_date)

    def test_on_mentee_rank_up_grants_mentor_karma(self):
        m = self._create_mentorship()
        initial_karma = self.mentor.karma

        Mentorship = self.env["gamification.mentorship"]
        Mentorship._on_mentee_rank_up(self.mentee)

        self.assertEqual(m.mentee_milestones_reached, 1)
        self.assertEqual(
            self.mentor.karma,
            initial_karma + m.mentor_karma_per_milestone,
        )

    def test_on_mentee_rank_up_only_active(self):
        m = self._create_mentorship()
        m.action_cancel()
        initial_karma = self.mentor.karma

        Mentorship = self.env["gamification.mentorship"]
        Mentorship._on_mentee_rank_up(self.mentee)

        self.assertEqual(self.mentor.karma, initial_karma)

    def test_get_suggested_mentors(self):
        Mentorship = self.env["gamification.mentorship"]
        suggestions = Mentorship.with_user(self.mentee).get_suggested_mentors(limit=5)

        self.assertIsInstance(suggestions, list)
        user_ids = [s["user_id"] for s in suggestions]
        self.assertNotIn(self.mentee.id, user_ids)
        for s in suggestions:
            self.assertGreater(s["karma"], self.mentee.karma)

    def test_get_suggested_mentors_excludes_own_mentee(self):
        self._create_mentorship()
        self.mentee.karma = self.mentor.karma + 100

        Mentorship = self.env["gamification.mentorship"]
        suggestions = Mentorship.with_user(self.mentor).get_suggested_mentors(limit=5)
        user_ids = [s["user_id"] for s in suggestions]
        self.assertNotIn(
            self.mentee.id,
            user_ids,
            "a user already mentored by the caller must not be suggested"
            " back as a mentor",
        )

    def test_display_name(self):
        m = self._create_mentorship()
        self.assertIn(self.mentor.name, m.display_name)
        self.assertIn(self.mentee.name, m.display_name)
