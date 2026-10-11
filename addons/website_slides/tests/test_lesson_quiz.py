from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestLessonQuiz(HttpCase):
    def _quiz_slide(self, channel_vals=None, slide_vals=None):
        channel = self.env["slide.channel"].create(
            {"name": "Quiz course", "enroll": "public", "is_published": True}
            | (channel_vals or {})
        )
        slide = self.env["slide.slide"].create(
            {
                "name": "Quiz lesson",
                "channel_id": channel.id,
                "slide_category": "quiz",
                "is_published": True,
            }
            | (slide_vals or {})
        )
        slide._ensure_quiz_survey()
        self.env["survey.question"].create(
            {
                "title": "Pick one",
                "survey_id": slide.survey_id.id,
                "question_type": "simple_choice",
                "suggested_answer_ids": [
                    Command.create(
                        {"value": "Right", "is_correct": True, "answer_score": 1}
                    ),
                    Command.create({"value": "Wrong", "is_correct": False}),
                ],
            }
        )
        return channel, slide

    def _completed(self, slide, user):
        return slide.slide_partner_ids.filtered(
            lambda slide_partner: slide_partner.partner_id == user.partner_id
        ).completed

    def test_an_attendee_answers_the_quiz_of_a_lesson_page(self):
        learner = new_test_user(
            self.env, login="quiz_learner", groups="base.group_portal"
        )
        channel, slide = self._quiz_slide()
        channel._action_add_members(learner.partner_id)

        self.start_tour(
            f"/slides/slide/{slide.id}",
            "slide_lesson_quiz_member",
            login="quiz_learner",
        )

    def test_answers_given_before_joining_are_submitted_after_joining(self):
        learner = new_test_user(
            self.env, login="quiz_joiner", groups="base.group_portal"
        )
        channel, slide = self._quiz_slide(slide_vals={"is_preview": True})

        self.start_tour(
            f"/slides/slide/{slide.id}",
            "slide_lesson_quiz_join_and_submit",
            login="quiz_joiner",
        )

        self.assertIn(learner.partner_id, channel.partner_ids)
        self.assertTrue(self._completed(slide, learner))

    def test_a_member_resets_a_completed_quiz(self):
        learner = new_test_user(
            self.env, login="quiz_resetter", groups="base.group_portal"
        )
        channel, slide = self._quiz_slide({"channel_type": "documentation"})
        channel._action_add_members(learner.partner_id)

        self.start_tour(
            f"/slides/slide/{slide.id}",
            "slide_lesson_quiz_complete_and_reset",
            login="quiz_resetter",
        )

        self.assertFalse(self._completed(slide, learner))
