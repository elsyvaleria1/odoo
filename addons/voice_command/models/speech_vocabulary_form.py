from odoo import api, models

from odoo.addons.speech.models.speech_vocabulary import spoken_words

LEARNED_MAX_CHARS = 60


class SpeechVocabularyForm(models.Model):
    _inherit = "speech.vocabulary.form"
    _access_verbs = {
        "learn": models.Verb(requires="read", methods=("learn",)),
    }

    @api.model
    def spoken_terms(self) -> list[dict]:
        return [
            {
                "phrases": form._spoken_phrases(),
                "means": form.word,
                "kind": form.pronunciation,
            }
            for form in self.search(
                [("company_id", "in", [*self.env.companies.ids, False])]
            )
        ]

    @api.model
    def learn(self, heard: str, meant: str) -> bool:
        user = self.env.user
        if (
            not user._is_internal()
            or not user.res_users_settings_id.voice_share_sentences
        ):
            return False
        heard_words, meant_words = spoken_words(heard or ""), spoken_words(meant or "")
        if (
            not heard_words
            or not meant_words
            or heard_words == meant_words
            or len(heard_words) > LEARNED_MAX_CHARS
            or len(meant_words) > LEARNED_MAX_CHARS
        ):
            return False
        learned = self.with_privilege(
            "voice_command.privilege_learn_term",
            reason="keep the reading a user chose, for an administrator to approve",
        ).with_context(active_test=False)
        word = learned.env["speech.vocabulary"]._word_as_said(
            meant, company=self.env.company
        )
        form = learned.search(
            [
                ("source", "=", "learned"),
                ("company_id", "=", self.env.company.id),
                ("phrases", "=", heard_words),
                ("vocabulary_id", "=", word.id),
            ],
            limit=1,
        )
        if form:
            form.confirmations += 1
            return True
        learned.create(
            {
                "phrases": heard_words,
                "vocabulary_id": word.id,
                "pronunciation": "local",
                "source": "learned",
                "company_id": self.env.company.id,
                "active": False,
                "confirmations": 1,
            }
        )
        return True

    def action_approve(self) -> None:
        self.active = True
