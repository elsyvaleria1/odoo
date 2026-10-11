import datetime

from freezegun import freeze_time

from odoo.tests.common import HttpCase, tagged

from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("-at_install", "post_install")
class TestHrAppraisalFeedbackController(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user = mail_new_test_user(
            cls.env,
            name="Test Appraisal",
            login="TestAppraisal",
            email="test@test.com",
            groups="base.group_user",
        )

        cls.user_appraisal_officer = mail_new_test_user(
            cls.env,
            name="Appraisal Officer",
            login="AppraisalOfficer",
            email="appraisal_officer@test.com",
            groups="hr_appraisal.group_hr_appraisal_user",
        )

        cls.user_manager = mail_new_test_user(
            cls.env,
            name="User Manager",
            login="UserManager",
            email="user_manager@test.com",
        )

        cls.user_employee = cls.env["hr.employee"].create(
            {"name": "Me Myself and I", "user_id": cls.user.id}
        )

        cls.appraisal_officer = cls.env["hr.employee"].create(
            {"name": "Mr. Appraisal Officer", "user_id": cls.user_appraisal_officer.id}
        )

        cls.manager = cls.env["hr.employee"].create(
            {"name": "Mr. Manager", "user_id": cls.user_manager.id}
        )

        cls.appraisal = cls.env["hr.appraisal"].create(
            {
                "employee_id": cls.user_employee.id,
                "manager_ids": [cls.manager.id],
                "state": "2_pending",
            }
        )

        cls.appraisal_survey = cls.env["survey.survey"].create(
            {
                "title": "appraisal feedback",
                "questions_layout": "one_page",
                "questions_selection": "all",
                "access_mode": "public",
                "survey_type": "appraisal",
            }
        )
        cls.question = cls.env["survey.question"].create(
            {
                "survey_id": cls.appraisal_survey.id,
                "title": "What is your name?",
                "sequence": 1,
                "question_type": "char_box",
            }
        )
        cls.survey_expired_text = (
            "This survey is now closed. Thank you for your interest!"
        )

    def test_appraisal_feedback_link_expiration(self):
        with freeze_time(datetime.date(2024, 9, 19)):
            feedback = self.env["wizard.hr.appraisal.send.feedback.survey"].create(
                {
                    "appraisal_id": self.appraisal.id,
                    "employee_ids": [self.user_employee.id],
                    "deadline": datetime.date(2024, 9, 20),
                    "survey_template_id": self.appraisal_survey.id,
                }
            )
            feedback.action_send()
            answer = self.env["survey.user_input"].search(
                [("appraisal_id", "=", self.appraisal.id)]
            )
            url = answer.get_start_url()

            self.authenticate(self.user.login, self.user.login)
            res = self.url_open(url)
            self.assertTrue(
                self.survey_expired_text not in str(res.content),
                "The link should not be expired before the deadline",
            )

            with freeze_time(datetime.date(2024, 9, 21)):
                res = self.url_open(url)
                self.assertTrue(
                    self.survey_expired_text in str(res.content),
                    "The link should be expired after the deadline",
                )

    def test_appraisal_feedback_link_for_managers(self):
        with freeze_time(datetime.date(2024, 9, 19)):
            feedback = self.env["wizard.hr.appraisal.send.feedback.survey"].create(
                {
                    "appraisal_id": self.appraisal.id,
                    "employee_ids": [self.user_employee.id],
                    "deadline": datetime.date(2024, 9, 19),
                    "survey_template_id": self.appraisal_survey.id,
                }
            )
            feedback.action_send()
            answer = self.env["survey.user_input"].search(
                [("appraisal_id", "=", self.appraisal.id)]
            )
            char_answer = "John Doe"
            self.env["survey.user_input.line"].create(
                {
                    "survey_id": self.appraisal_survey.id,
                    "user_input_id": answer.id,
                    "question_id": self.question.id,
                    "answer_type": "char_box",
                    "value_char_box": char_answer,
                    "skipped": False,
                }
            )
            url = answer.get_print_url()
            with freeze_time(datetime.date(2024, 9, 21)):
                self.authenticate(
                    self.user_appraisal_officer.login, self.user_appraisal_officer.login
                )
                res = self.url_open(url)
                self.assertTrue(
                    self.survey_expired_text not in str(res.content),
                    "A user in Appraisal:Officer group should be able to access the survey answers after the deadline",
                )
                self.assertTrue(
                    char_answer in str(res.content),
                    "A user in Appraisal:Officer group should be able to see the survey answers",
                )

            with freeze_time(datetime.date(2024, 9, 21)):
                self.authenticate(self.user_manager.login, self.user_manager.login)
                res = self.url_open(url)
                self.assertTrue(
                    self.survey_expired_text not in str(res.content),
                    "The manager of an appraisal should be able to access the survey answers after the deadline",
                )
                self.assertTrue(
                    char_answer in str(res.content),
                    "The manager of an appraisal should be able to see the survey answers",
                )

    def test_appraisal_results_page_access(self):
        answer = self.env["survey.user_input"].create(
            {
                "survey_id": self.appraisal_survey.id,
                "appraisal_id": self.appraisal.id,
                "partner_id": self.user_manager.partner_id.id,
            }
        )
        answer._mark_done()
        url = f"/appraisal/{self.appraisal.id}/results"

        self.authenticate(self.user.login, self.user.login)
        res = self.url_open(url)
        self.assertEqual(
            res.status_code,
            403,
            "The appraised employee must be refused with a real status, not a 200",
        )

        self.authenticate(
            self.user_appraisal_officer.login, self.user_appraisal_officer.login
        )
        res = self.url_open(url)
        self.assertEqual(
            res.status_code,
            200,
            "An Appraisal Officer should reach the results page",
        )

    def test_appraisal_results_page_rejects_a_broken_filter(self):
        self.authenticate(
            self.user_appraisal_officer.login, self.user_appraisal_officer.login
        )
        res = self.url_open(
            f"/survey/results/{self.appraisal_survey.id}?appraisal_id=abc"
        )
        self.assertNotEqual(
            res.status_code, 500, "A bad appraisal_id must not raise a server error"
        )

    def test_appraisal_results_page_hides_peer_answer_tokens(self):
        peer_user = mail_new_test_user(
            self.env,
            name="Peer Rater",
            login="PeerRater",
            email="peer_rater@test.com",
            groups="base.group_user",
        )
        rater_user = mail_new_test_user(
            self.env,
            name="The Rater",
            login="TheRater",
            email="the_rater@test.com",
            groups="base.group_user",
        )
        peer_employee, rater_employee = self.env["hr.employee"].create(
            [
                {"name": "Peer Rater", "user_id": peer_user.id},
                {"name": "The Rater", "user_id": rater_user.id},
            ]
        )
        self.appraisal.employee_feedback_ids = [
            (6, 0, (peer_employee | rater_employee).ids)
        ]
        peer_answer, rater_answer = self.env["survey.user_input"].create(
            [
                {
                    "survey_id": self.appraisal_survey.id,
                    "appraisal_id": self.appraisal.id,
                    "partner_id": peer_user.partner_id.id,
                },
                {
                    "survey_id": self.appraisal_survey.id,
                    "appraisal_id": self.appraisal.id,
                    "partner_id": rater_user.partner_id.id,
                },
            ]
        )
        (peer_answer | rater_answer)._mark_done()
        url = f"/appraisal/{self.appraisal.id}/results"

        self.authenticate(rater_user.login, rater_user.login)
        page = self.url_open(url).text
        self.assertNotIn(
            peer_answer.access_token,
            page,
            "a rater must not be handed a peer's answer token",
        )
        self.assertIn(
            rater_answer.access_token,
            page,
            "a rater must still reach their own answer",
        )

        self.authenticate(self.user_manager.login, self.user_manager.login)
        page = self.url_open(url).text
        for token in (peer_answer.access_token, rater_answer.access_token):
            self.assertIn(token, page, "a manager still sees every rater")

    def test_appraisal_results_page_admits_a_system_administrator(self):
        sysadmin = mail_new_test_user(
            self.env,
            name="Sys Admin",
            login="SysAdmin",
            email="sys_admin@test.com",
            groups="base.group_user,base.group_system",
        )
        self.assertFalse(
            sysadmin.has_group("hr_appraisal.group_hr_appraisal_user"),
            "the gap only exists for a sysadmin who is not also an officer",
        )
        self.assertNotIn(sysadmin, self.appraisal.manager_ids.user_id)

        answer = self.env["survey.user_input"].create(
            {
                "survey_id": self.appraisal_survey.id,
                "appraisal_id": self.appraisal.id,
                "partner_id": self.user_manager.partner_id.id,
            }
        )
        answer._mark_done()

        self.authenticate(sysadmin.login, sysadmin.login)
        res = self.url_open(f"/appraisal/{self.appraisal.id}/results")
        self.assertEqual(
            res.status_code,
            200,
            "a system administrator must not be refused by the second gate",
        )
        self.assertIn(
            answer.access_token,
            res.text,
            "and must see the answers the first gate granted them",
        )
