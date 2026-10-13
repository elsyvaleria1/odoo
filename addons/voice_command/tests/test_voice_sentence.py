from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.voice_command.models.voice_sentence import (
    SENTENCE_MAX_CHARS,
    SENTENCE_RETENTION_DAYS,
)


@tagged("post_install", "-at_install")
class TestVoiceSentence(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.speaker = new_test_user(cls.env, login="voice_speaker")
        cls.portal = new_test_user(
            cls.env, login="voice_portal", groups="base.group_portal"
        )
        cls.Sentence = cls.env["voice.sentence"]
        cls.existing = cls.Sentence.search([])

    def _share(self, user, shared=True):
        settings = self.env["res.users.settings"]._get_or_create_for_user(user)
        settings.voice_share_sentences = shared

    def _new_rows(self):
        return self.Sentence.search([("id", "not in", self.existing.ids)], order="id")

    def _record(self, user, answered_by, text="abre ventas"):
        return self.Sentence.with_user(user).record(
            answered_by, text, spoken=True, res_model="sale.order", view_type="form"
        )

    def test_nothing_is_kept_for_a_user_who_did_not_choose_to_share(self):
        self._share(self.speaker, shared=False)
        self.assertFalse(self._record(self.speaker, "none"))
        self.assertFalse(self._new_rows())

    def test_the_words_are_kept_only_when_the_grammar_missed(self):
        self._share(self.speaker)
        self.assertTrue(self._record(self.speaker, "grammar", "sin pagar"))
        self.assertTrue(self._record(self.speaker, "none", "el perro come"))
        self.assertTrue(self._record(self.speaker, "model", "x" * 500))
        self.assertTrue(self._record(self.speaker, "correction", "Descarpar"))
        self.assertTrue(self._record(self.speaker, "english", "chou nambers"))
        rows = self._new_rows()
        self.assertEqual(
            rows.mapped("answered_by"),
            ["grammar", "none", "model", "correction", "english"],
        )
        self.assertEqual(rows[3].text, "Descarpar")
        self.assertEqual(rows[4].text, "chou nambers")
        self.assertEqual(rows[0].text, False)
        self.assertEqual(rows[1].text, "el perro come")
        self.assertEqual(len(rows[2].text), SENTENCE_MAX_CHARS)
        self.assertEqual(rows[1].res_model, "sale.order")
        self.assertEqual(rows.company_id, self.speaker.company_id)
        self.assertTrue(rows[1].spoken)

    def test_a_shared_sentence_names_no_one(self):
        self.assertNotIn("create_uid", self.Sentence._fields)
        self.assertNotIn("create_date", self.Sentence._fields)

    def test_an_unknown_outcome_or_a_portal_user_is_refused(self):
        self._share(self.speaker)
        self._share(self.portal)
        self.assertFalse(self._record(self.speaker, "guessed"))
        self.assertFalse(self._record(self.portal, "none"))
        self.assertFalse(self._new_rows())

    def test_only_administrators_read_them_and_nobody_writes_one_directly(self):
        self._share(self.speaker)
        self._record(self.speaker, "none")
        with self.assertRaises(AccessError):
            self.Sentence.with_user(self.speaker).search([]).mapped("text")
        with self.assertRaises(AccessError):
            self.Sentence.with_user(self.speaker).create(
                {"day": fields.Date.today(), "answered_by": "none"}
            )
        admin = self.env.ref("base.user_admin")
        self.assertEqual(
            self.Sentence.with_user(admin).search([]) - self.existing,
            self._new_rows(),
        )
        self.assertEqual(len(self._new_rows()), 1)

    def test_a_sentence_is_forgotten_after_its_retention(self):
        today = fields.Date.today()
        old, kept = self.Sentence.create(
            [
                {
                    "day": today - timedelta(days=SENTENCE_RETENTION_DAYS + 1),
                    "answered_by": "none",
                },
                {
                    "day": today - timedelta(days=SENTENCE_RETENTION_DAYS - 1),
                    "answered_by": "none",
                },
            ]
        )
        self.Sentence._gc_old_sentences()
        self.assertFalse(old.exists())
        self.assertTrue(kept.exists())
