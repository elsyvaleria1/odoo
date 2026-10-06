from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAppraisalSurveyActions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager_user = cls.env["res.users"].create(
            {"name": "Appraisal Manager", "login": "appraisal_manager"}
        )
        cls.manager = cls.env["hr.employee"].create(
            {"name": "Manager", "user_id": cls.manager_user.id}
        )
        cls.employee = cls.env["hr.employee"].create({"name": "Rated Employee"})
        cls.appraisal = cls.env["hr.appraisal"].create(
            {
                "employee_id": cls.employee.id,
                "manager_ids": [Command.link(cls.manager.id)],
            }
        )
        cls.survey_a, cls.survey_b = cls.env["survey.survey"].create(
            [
                {"title": "Feedback A", "survey_type": "appraisal"},
                {"title": "Feedback B", "survey_type": "appraisal"},
            ]
        )
        cls.input_a = cls.env["survey.user_input"].create(
            {"survey_id": cls.survey_a.id, "appraisal_id": cls.appraisal.id}
        )

    def test_appraisal_managers_computed_from_inputs(self):
        """Check that appraisal managers propagate to the survey access list."""
        self.assertIn(self.manager_user, self.survey_a.appraisal_manager_user_ids)
        self.assertFalse(self.survey_b.appraisal_manager_user_ids)

    def test_open_single_input_url_contract(self):
        """Check the print URL carries the survey token, the answer token and
        the review flag."""
        action = self.input_a.action_view_survey_inputs()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn(f"/survey/print/{self.survey_a.access_token}", action["url"])
        self.assertIn(f"answer_token={self.input_a.access_token}", action["url"])
        self.assertIn("review=True", action["url"])

    def test_open_results_without_surveys_is_rejected(self):
        """Check the no-survey boundary raises instead of returning a broken
        action."""
        empty = self.env["survey.user_input"].with_context(active_id=-1)
        with self.assertRaises(ValidationError):
            empty.action_view_appraisal_survey_results()

    def test_open_results_without_selection_is_rejected(self):
        """Check that no selection and no active_id is refused, instead of
        searching for answers whose appraisal_id is False."""
        orphan = self.env["survey.user_input"].create({"survey_id": self.survey_a.id})
        self.assertFalse(orphan.appraisal_id)
        with self.assertRaises(ValidationError):
            self.env["survey.user_input"].with_context(
                {}
            ).action_view_appraisal_survey_results()

    def test_open_results_single_survey_returns_url(self):
        """Check that a single-survey appraisal opens the results URL
        directly."""
        action = self.input_a.action_view_appraisal_survey_results()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn(f"/survey/results/{self.survey_a.id}", action["url"])
        self.assertIn(f"appraisal_id={self.appraisal.id}", action["url"])

    def test_open_results_multiple_surveys_opens_selector(self):
        """Check that inputs over several surveys route to the selector
        wizard with the inputs preloaded."""
        input_b = self.env["survey.user_input"].create(
            {"survey_id": self.survey_b.id, "appraisal_id": self.appraisal.id}
        )
        both = self.input_a + input_b
        action = both.action_view_appraisal_survey_results()
        self.assertEqual(action["res_model"], "wizard.survey.user_input.view.result")
        self.assertEqual(
            set(action["context"]["default_survey_input_ids"]), set(both.ids)
        )

    def test_ask_feedback_rejects_mixed_batches(self):
        """Check both multi-appraisal and multi-template batches are rejected."""
        with self.subTest("multi-appraisal batch"):
            other_appraisal = self.env["hr.appraisal"].create(
                {"employee_id": self.employee.id}
            )
            cross_appraisal = self.input_a + self.env["survey.user_input"].create(
                {"survey_id": self.survey_a.id, "appraisal_id": other_appraisal.id}
            )
            with self.assertRaises(ValidationError):
                cross_appraisal.action_ask_feedback()

        with self.subTest("multi-template batch"):
            cross_survey = self.input_a + self.env["survey.user_input"].create(
                {"survey_id": self.survey_b.id, "appraisal_id": self.appraisal.id}
            )
            with self.assertRaises(ValidationError):
                cross_survey.action_ask_feedback()

    def test_select_survey_wizard_defaults_and_filtering(self):
        """Check the selector wizard derives its allowed surveys, defaults to
        the first and filters results by the chosen template."""
        input_b = self.env["survey.user_input"].create(
            {"survey_id": self.survey_b.id, "appraisal_id": self.appraisal.id}
        )
        with self.subTest("defaults"):
            # new(): in-memory record as the dialog builds it — the stored
            # compute chain fires without hitting the NOT NULL constraint at
            # insert
            wizard = self.env["wizard.survey.user_input.view.result"].new(
                {"survey_input_ids": [Command.set((self.input_a + input_b).ids)]}
            )
            self.assertEqual(
                wizard.allowed_survey_template_ids._origin,
                self.survey_a + self.survey_b,
            )
            self.assertEqual(wizard.survey_template_id._origin, self.survey_a)

        with self.subTest("filtering by chosen template"):
            saved = self.env["wizard.survey.user_input.view.result"].create(
                {
                    "survey_input_ids": [Command.set((self.input_a + input_b).ids)],
                    "survey_template_id": self.survey_b.id,
                }
            )
            action = saved.action_see_results()
            self.assertIn(f"/survey/results/{self.survey_b.id}", action["url"])
