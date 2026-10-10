from lxml import html

from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

from odoo.addons.website_slides.tests import common


@tagged("post_install", "-at_install")
class TestQuizEditing(HttpCase, common.SlidesCase):
    def _answers_of(self, quiz_data, question):
        return next(q for q in quiz_data["slide_questions"] if q["id"] == question.id)[
            "answer_ids"
        ]

    def _rpc(self, route, params):
        response = self.url_open(
            route,
            data=json_dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"},
        )
        return response.json()["result"]

    def test_the_gate_is_not_the_designer_group(self):
        self.assertFalse(
            self.user_officer.has_group("website.group_website_designer"),
            "an eLearning officer is not a website designer",
        )
        self.assertFalse(
            self.user_manager.has_group("website.group_website_designer"),
            "an eLearning manager is not a website designer either",
        )
        self.assertTrue(
            self.env.ref("base.user_admin").has_group("website.group_website_designer"),
            "admin is -- which is why this never showed up in a demo database",
        )

    def test_publisher_receives_is_correct(self):
        self.authenticate("user_officer", "user_officer")
        data = self._rpc("/slides/slide/quiz/get", {"slide_id": self.slide_3.id})
        answers = self._answers_of(data, self.question_1)
        by_value = {answer["text_value"]: answer for answer in answers}
        self.assertTrue(
            by_value[self.answer_1.value]["is_correct"],
            "the publisher must be told which answer is correct, or editing "
            "the question silently erases it",
        )
        self.assertFalse(by_value[self.answer_2.value]["is_correct"])

    def test_learner_does_not_receive_is_correct(self):
        self.channel.sudo()._action_add_members(self.user_portal.partner_id)
        self.authenticate("user_portal", "user_portal")
        data = self._rpc("/slides/slide/quiz/get", {"slide_id": self.slide_3.id})
        answers = self._answers_of(data, self.question_1)
        self.assertTrue(
            all(answer["is_correct"] is None for answer in answers),
            "an attendee who has not passed the quiz must not be handed the key",
        )

    def test_editing_a_question_keeps_the_correct_answer(self):
        self.authenticate("user_officer", "user_officer")
        correct_value = self.answer_1.value
        data = self._rpc("/slides/slide/quiz/get", {"slide_id": self.slide_3.id})
        question = next(
            q for q in data["slide_questions"] if q["id"] == self.question_1.id
        )

        result = self._rpc(
            "/slides/slide/quiz/question_add_or_update",
            {
                "slide_id": self.slide_3.id,
                "question": question["question"],
                "sequence": 1,
                "existing_question_id": question["id"],
                "answer_ids": [
                    {
                        "sequence": index + 1,
                        "text_value": answer["text_value"],
                        "is_correct": bool(answer["is_correct"]),
                        "comment": answer["comment"] or "",
                    }
                    for index, answer in enumerate(question["answer_ids"])
                ],
            },
        )

        answers = self.slide_3.sudo().survey_id.question_ids.suggested_answer_ids
        correct = answers.filtered("is_correct")
        self.assertEqual(
            correct.value,
            correct_value,
            "editing a question must not erase which answer is correct",
        )
        self.assertEqual(correct.answer_score, 1.0)
        (fragment,) = result["fragments"]
        self.assertEqual(
            fragment["key"], f"website_slides.quiz_question.{self.question_1.id}"
        )
        self.assertIn(question["question"], fragment["html"])
        self.assertTrue(self.question_1.exists(), "an edited question keeps its id")

    def test_question_add_or_update_answers_a_dict_on_every_outcome(self):
        self.authenticate("user_officer", "user_officer")
        missing_slide = self._rpc(
            "/slides/slide/quiz/question_add_or_update",
            {
                "slide_id": -1,
                "question": "Q",
                "sequence": 1,
                "answer_ids": [],
            },
        )
        self.assertEqual(
            (missing_slide["fragments"], missing_slide["data"]),
            ([], {"error": "slide_wrong"}),
        )

    def _add_question(self, placeholder):
        return self._rpc(
            "/slides/slide/quiz/question_add_or_update",
            {
                "slide_id": self.slide_3.id,
                "question": "New question?",
                "sequence": 3,
                "placeholder": placeholder,
                "answer_ids": [
                    {
                        "sequence": 1,
                        "text_value": "Yes",
                        "is_correct": True,
                        "comment": "",
                    },
                    {
                        "sequence": 2,
                        "text_value": "No",
                        "is_correct": False,
                        "comment": "",
                    },
                ],
            },
        )

    def test_a_new_question_takes_the_placeholder_s_place_and_leaves_the_next(self):
        self.authenticate("user_officer", "user_officer")
        placeholder = f"website_slides.quiz_question_new.{self.slide_3.id}.7"

        result = self._add_question(placeholder)

        (fragment,) = result["fragments"]
        self.assertEqual(fragment["key"], placeholder)
        root = html.fromstring(fragment["html"])
        created = self.quiz_survey.sudo().question_ids.filtered(
            lambda question: question.title == "New question?"
        )
        self.assertTrue(created)
        self.assertEqual(
            root.xpath("//div[@data-fragment]/@data-fragment"),
            [
                placeholder,
                f"website_slides.quiz_question.{created.id}",
                f"website_slides.quiz_question_new.{self.slide_3.id}.8",
            ],
        )

    def test_a_placeholder_of_another_slide_is_refused_and_nothing_is_created(self):
        self.authenticate("user_officer", "user_officer")
        before = self.quiz_survey.sudo().question_ids

        response = self.url_open(
            "/slides/slide/quiz/question_add_or_update",
            data=json_dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": {
                        "slide_id": self.slide_3.id,
                        "question": "Stray?",
                        "sequence": 3,
                        "placeholder": "website_slides.quiz_question_new.999999.1",
                        "answer_ids": [],
                    },
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        self.assertIn("error", response.json())
        self.quiz_survey.invalidate_recordset()
        self.assertEqual(self.quiz_survey.sudo().question_ids, before)

    def test_the_lesson_page_offers_a_region_per_question_and_a_placeholder(self):
        self.authenticate("user_officer", "user_officer")

        page = html.fromstring(
            self.url_open(f"/slides/slide/{self.slide_3.id}").content
        )

        keys = page.xpath("//*[@data-fragment]/@data-fragment")
        for question in self.quiz_survey.sudo().question_ids:
            self.assertIn(f"website_slides.quiz_question.{question.id}", keys)
        self.assertIn(
            f"website_slides.quiz_question_new.{self.slide_3.id}."
            f"{len(self.quiz_survey.sudo().question_ids) + 1}",
            keys,
        )

    def test_a_question_is_added_then_edited_in_place_from_the_lesson(self):
        lesson = self.env["slide.slide"].create(
            {
                "name": "Quiz article",
                "channel_id": self.channel.id,
                "slide_category": "article",
                "html_content": "<p>Read, then answer</p>",
                "is_published": True,
            }
        )
        self.start_tour(
            f"/slides/slide/{lesson.id}",
            "slides_quiz_edit_in_place",
            login="user_officer",
        )

        questions = lesson.sudo().survey_id.question_ids
        added = questions.filtered(lambda q: q.title == "Tour question, edited?")
        self.assertEqual(len(added), 1)
        self.assertEqual(
            added.suggested_answer_ids.filtered("is_correct").value, "Right"
        )
