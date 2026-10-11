from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.base.models.access_link import hash_token
from odoo.addons.survey.tests import common


@tagged("post_install", "-at_install", "access_link")
class TestSurveyInvitationLinks(common.TestSurveyCommon, HttpCase):
    def _links(self, answer):
        return (
            self.env["access.link"]
            .sudo()
            .search(
                [("res_model", "=", "survey.user_input"), ("res_id", "=", answer.id)]
            )
        )

    def _mailed_token(self, answer):
        return parse_qs(urlparse(answer.get_start_url()).query)["answer_token"][0]

    def _start(self, token, survey=None):
        return self.url_open(
            f"/survey/start/{(survey or self.survey).access_token}?answer_token={token}"
        )

    def test_an_invited_partner_is_mailed_a_link_not_the_answers_session(self):
        deadline = fields.Datetime.now().replace(microsecond=0) + timedelta(days=9)
        answer = self._add_answer(self.survey, self.customer, deadline=deadline)
        link = self._links(answer)
        self.assertEqual(
            (len(link), link.partner_id, link.role, link.cause, link.date_to),
            (
                1,
                self.customer,
                "comment",
                "notification",
                deadline + timedelta(days=30),
            ),
        )
        token = self._mailed_token(answer)
        self.assertEqual(link.token_hash, hash_token(token))
        self.assertNotEqual(token, answer.access_token)
        self.assertEqual(self._mailed_token(answer), token, "reused")
        self.authenticate(None, None)
        response = self._start(token)
        self.assertEqual(response.status_code, 200)
        self.assertIn(answer.access_token, response.text, "the page runs its session")

    def test_moving_the_deadline_moves_the_invitation_link(self):
        now = fields.Datetime.now().replace(microsecond=0)
        answer = self._add_answer(
            self.survey, self.customer, deadline=now + timedelta(days=9)
        )
        for deadline in (now + timedelta(days=730), now + timedelta(days=2)):
            with self.subTest(deadline=deadline):
                answer.deadline = deadline
                self.assertEqual(
                    self._links(answer).date_to, deadline + timedelta(days=30)
                )

    def test_an_anonymous_answer_keeps_its_own_token(self):
        answer = self._add_answer(self.survey, False)
        self.assertFalse(self._links(answer))
        self.assertEqual(self._mailed_token(answer), answer.access_token)

    def test_an_invitation_opens_its_own_survey_only(self):
        answer = self._add_answer(self.survey, self.customer)
        other = self.survey.copy()
        token = self._mailed_token(answer)
        self.authenticate(None, None)
        self.assertNotIn(answer.access_token, self._start(token, other).text)
        self._links(answer).date_to = fields.Datetime.now() - timedelta(seconds=1)
        self.assertNotIn(answer.access_token, self._start(token).text, "expired")
