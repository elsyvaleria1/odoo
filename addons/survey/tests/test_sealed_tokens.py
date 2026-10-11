from odoo.db.schema import column_exists
from odoo.tests import TransactionCase, tagged

from odoo.addons.base.models.mixin_bearer_token import hash_bearer_token


@tagged("post_install", "-at_install")
class TestSealedSurveyTokens(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.survey = cls.env["survey.survey"].create(
            {"title": "Sealed", "access_mode": "public"}
        )
        cls.answer = cls.env["survey.user_input"].create({"survey_id": cls.survey.id})

    def test_neither_token_is_kept_in_clear(self):
        for table in ("survey_survey", "survey_user_input"):
            self.assertFalse(column_exists(self.env.cr, table, "access_token"), table)
        for record in (self.survey, self.answer):
            token = record.access_token
            self.assertTrue(token)
            self.assertEqual(record.access_token_hash, hash_bearer_token(token))
            self.assertNotIn(token, record.access_token_sealed)

    def test_a_token_finds_its_survey_and_its_answer(self):
        Survey = self.env["survey.survey"]
        self.assertEqual(
            Survey.search([("access_token", "=", self.survey.access_token)]),
            self.survey,
        )
        self.assertEqual(
            self.env["survey.user_input"].search(
                [("access_token", "=", self.answer.access_token)]
            ),
            self.answer,
        )
        self.assertFalse(Survey.search([("access_token", "=", "not-a-token")]))

    def test_the_short_link_is_the_token_s_first_characters(self):
        prefix = self.survey.access_token[: self.survey.SHORT_TOKEN_LENGTH]
        self.assertEqual(self.survey.short_link_code, prefix)
        self.assertEqual(
            self.env["survey.survey"]._resolve_short_token(prefix), self.survey
        )
        self.survey.access_token = "f00dfeed-0000-4000-8000-000000000000"
        self.assertEqual(self.survey.short_link_code, "f00dfe")
        self.assertEqual(
            self.env["survey.survey"]._resolve_short_token("f00dfe"), self.survey
        )
        self.assertFalse(self.env["survey.survey"]._resolve_short_token(prefix))
