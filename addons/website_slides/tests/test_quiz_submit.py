from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestQuizSubmit(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.learner = new_test_user(
            cls.env, login="quiz_submitter", groups="base.group_portal"
        )
        cls.channel = cls.env["slide.channel"].create(
            {"name": "Quiz rules", "enroll": "public", "is_published": True}
        )
        cls.slide = cls.env["slide.slide"].create(
            {
                "name": "Graded quiz",
                "channel_id": cls.channel.id,
                "slide_category": "quiz",
                "is_published": True,
                "is_preview": True,
                "quiz_first_attempt_reward": 10,
            }
        )
        cls.slide._ensure_quiz_survey()
        question = cls.env["survey.question"].create(
            {
                "title": "Pick",
                "survey_id": cls.slide.survey_id.id,
                "question_type": "simple_choice",
                "suggested_answer_ids": [
                    Command.create(
                        {"value": "right", "is_correct": True, "answer_score": 1}
                    ),
                    Command.create(
                        {"value": "wrong", "is_correct": False, "comment": "no"}
                    ),
                ],
            }
        )
        cls.right, cls.wrong = question.suggested_answer_ids

    def _submit(self, *answers):
        return self.call_jsonrpc(
            "/slides/slide/quiz/submit",
            {"slide_id": self.slide.id, "answer_ids": [a.id for a in answers]},
        )

    def _attempts(self):
        return (
            self.env["slide.slide.partner"]
            .search(
                [
                    ("slide_id", "=", self.slide.id),
                    ("partner_id", "=", self.learner.partner_id.id),
                ]
            )
            .quiz_attempts_count
        )

    def test_a_previewing_visitor_learns_nothing_about_the_answers(self):
        self.authenticate("quiz_submitter", "quiz_submitter")

        result = self._submit(self.wrong)

        self.assertEqual(result, {"error": "slide_quiz_not_member"})

    def test_every_answer_to_one_question_is_not_an_attempt(self):
        self.channel._action_add_members(self.learner.partner_id)
        self.authenticate("quiz_submitter", "quiz_submitter")

        result = self._submit(self.right, self.wrong)

        self.assertEqual(result, {"error": "slide_quiz_incomplete"})
        self.assertEqual(self._attempts(), 0)

    def test_a_failed_attempt_wins_no_karma(self):
        self.channel._action_add_members(self.learner.partner_id)
        self.authenticate("quiz_submitter", "quiz_submitter")

        failed = self._submit(self.wrong)
        passed = self._submit(self.right)

        self.assertEqual((failed["completed"], failed["quizKarmaWon"]), (False, 0))
        self.assertEqual(passed["completed"], True)
        self.assertEqual(passed["quizKarmaWon"], self.slide.quiz_second_attempt_reward)
        self.assertEqual(self._attempts(), 2)
