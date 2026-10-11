from __future__ import annotations

import re
from collections.abc import Iterable

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.text import remove_accents

KEYTERM_LIMIT = 100

_PHRASE_SEPARATOR = re.compile(r"\s*;\s*")
_WORDS = re.compile(r"\w+")


def spoken_words(phrase: str) -> str:
    return " ".join(_WORDS.findall(remove_accents(phrase).lower()))


class SpeechVocabulary(models.Model):
    _name = "speech.vocabulary"
    _description = "Speech Vocabulary"
    _order = "sequence, name"

    name = fields.Char(required=True)
    kind = fields.Selection(
        selection=[
            ("term", "Term"),
            ("product", "Product"),
            ("person", "Person"),
            ("place", "Place"),
            ("company", "Company"),
        ],
        default="term",
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        help="Empty means every company",
    )
    form_ids = fields.One2many(
        comodel_name="speech.vocabulary.form",
        inverse_name="vocabulary_id",
        string="Spoken forms",
        help="How people say this word when it is not said as written.",
    )

    _name_company_unique = models.Constraint(
        "UNIQUE NULLS NOT DISTINCT (name, company_id)",
        "A vocabulary term is already registered for this company.",
    )

    @api.model
    def _keyterms(self, company=None, limit=KEYTERM_LIMIT) -> list[str]:
        company = company or self.env.company
        return (
            self.sudo()
            .search([("company_id", "in", (company.id, False))], limit=limit)
            .mapped("name")
        )

    @api.model
    def _word_as_said(self, text: str, company=None) -> SpeechVocabulary:
        """The word a phrase is, however it is accented or cased; created from
        the phrase as given when no word sounds like it."""
        said = spoken_words(text)
        company_id = company.id if company else False
        words = self.with_context(active_test=False).search(
            [("company_id", "in", [company_id, False])]
        )
        return next(
            (word for word in words if spoken_words(word.name) == said), None
        ) or self._get_or_create_words([text], company=company)

    @api.model
    def _get_or_create_words(
        self, names: Iterable[str], kind: str = "term", company=None
    ) -> SpeechVocabulary:
        """The words by name -- the company's own, else the shared one --
        created where missing: two modules that need the same word share it
        instead of colliding on it."""
        Vocabulary = self.with_context(active_test=False)
        company_id = company.id if company else False
        wanted = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        found = Vocabulary.search(
            [("name", "in", wanted), ("company_id", "in", [company_id, False])]
        )
        by_name = {}
        for word in found.sorted(lambda w: w.company_id.id != company_id):
            by_name.setdefault(word.name, word)
        missing = [name for name in wanted if name not in by_name]
        for word in Vocabulary.create(
            [{"name": name, "kind": kind, "company_id": company_id} for name in missing]
        ):
            by_name[word.name] = word
        return self.browse([by_name[name].id for name in wanted])


class SpeechVocabularyForm(models.Model):
    _name = "speech.vocabulary.form"
    _description = "Spoken Form of a Vocabulary Word"
    _order = "phrases, id"
    _rec_name = "phrases"
    # a learned form names no one: who confirmed it is not kept
    _log_access = False

    vocabulary_id = fields.Many2one(
        comodel_name="speech.vocabulary",
        string="Vocabulary Entry",
        index=True,
        required=True,
        ondelete="cascade",
    )
    word = fields.Char(
        compute="_compute_word",
        inverse="_inverse_word",
        help="The word as the screens spell it; a word not in the vocabulary "
        "yet is added to it.",
    )
    phrases = fields.Char(
        required=True,
        help="What is said, as a recogniser writes it; each form separated by a "
        "semicolon: checa; checar; checalo.",
    )
    pronunciation = fields.Selection(
        selection=[
            ("local", "As written"),
            ("word", "English word"),
            ("acronym", "Acronym"),
        ],
        default="local",
        required=True,
        help="An English word or an acronym is also matched as a Mexican speaker "
        "says it (status: estatus; PO: pe o); a form said as written only as "
        "written.",
    )
    source = fields.Selection(
        selection=[
            ("seed", "Seed"),
            ("admin", "Administrator"),
            ("learned", "Learned"),
        ],
        default="admin",
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        ondelete="cascade",
        help="Leave empty to use the form in every company.",
    )
    active = fields.Boolean(default=True)
    confirmations = fields.Integer(
        readonly=True,
        help="How many times a user who shares what they say chose this reading "
        "from a list. A learned form is used once an administrator approves it.",
    )

    @api.depends("vocabulary_id.name")
    def _compute_word(self) -> None:
        for form in self:
            form.word = form.vocabulary_id.name

    def _inverse_word(self) -> None:
        for form in self:
            if form.word:
                form.vocabulary_id = self.env["speech.vocabulary"]._word_as_said(
                    form.word, company=form.company_id or None
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            word = vals.pop("word", None)
            if word and not vals.get("vocabulary_id"):
                company = self.env["res.company"].browse(vals.get("company_id"))
                vals["vocabulary_id"] = (
                    self.env["speech.vocabulary"]
                    ._word_as_said(word, company=company or None)
                    .id
                )
        return super().create(vals_list)

    def _spoken_phrases(self) -> list[str]:
        self.check_singleton()
        return [
            words
            for words in map(spoken_words, _PHRASE_SEPARATOR.split(self.phrases or ""))
            if words
        ]

    @api.constrains("phrases", "vocabulary_id", "company_id", "active")
    def _check_phrases(self) -> None:
        for form in self:
            if not form._spoken_phrases() or not spoken_words(form.word or ""):
                raise ValidationError(
                    form.env._("A spoken form needs a phrase and the word it means.")
                )
        forms = self.search([("company_id", "in", [*self.company_id.ids, False])])
        for form in self.filtered("active"):
            mine = set(form._spoken_phrases())
            for other in forms - form:
                if other.company_id and form.company_id != other.company_id:
                    continue
                shared = mine & set(other._spoken_phrases())
                if shared and spoken_words(other.word) != spoken_words(form.word):
                    raise ValidationError(
                        form.env._(
                            "“%(phrase)s” already means “%(means)s”.",
                            phrase=min(shared),
                            means=other.word,
                        )
                    )
