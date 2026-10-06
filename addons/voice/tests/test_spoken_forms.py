import re
from pathlib import Path

from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, new_test_user, tagged

MODULE = Path(__file__).parent.parent
SEED_ROW = re.compile(r"\[\s*(\"[^\"]*\"),\s*(\"[^\"]*\"),\s*(\"[^\"]*\"),?\s*\]")


@tagged("post_install", "-at_install")
class TestSpokenForms(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Term = cls.env["speech.vocabulary.form"]
        cls.other_company = cls.env["res.company"].create({"name": "Voice Elsewhere"})
        cls.user = new_test_user(cls.env, login="voice_terms")

    def test_a_user_reads_the_shared_terms_and_those_of_their_company(self):
        self.Term.create(
            {"phrases": "dasbor; dashbord", "word": "tableros", "pronunciation": "word"}
        )
        self.Term.create(
            {
                "phrases": "bodega",
                "word": "almacén",
                "pronunciation": "local",
                "company_id": self.other_company.id,
            }
        )
        terms = self.Term.with_user(self.user).spoken_terms()
        self.assertIn(
            {"phrases": ["dasbor", "dashbord"], "means": "tableros", "kind": "word"},
            terms,
        )
        self.assertNotIn("bodega", [p for term in terms for p in term["phrases"]])

    def test_a_phrase_is_kept_as_it_is_spoken(self):
        term = self.Term.create({"phrases": " Chécalo ;  Big-Bag; ", "word": "revisa"})
        self.assertEqual(term._spoken_phrases(), ["checalo", "big bag"])

    def test_one_phrase_cannot_mean_two_things(self):
        self.Term.create({"phrases": "setea", "word": "establece"})
        with self.assertRaises(ValidationError):
            self.Term.create({"phrases": "Seteá; setear", "word": "borra"})
        self.Term.create({"phrases": "setea", "word": "Establece"})

    def test_a_company_term_may_differ_from_another_companys(self):
        for company in (self.env.company, self.other_company):
            self.Term.create(
                {"phrases": "bodega", "word": company.name, "company_id": company.id}
            )

    def test_a_term_needs_words_on_both_sides(self):
        with self.assertRaises(ValidationError):
            self.Term.create({"phrases": " ; ", "word": "muestra"})
        with self.assertRaises(ValidationError):
            self.Term.create({"phrases": "checa", "word": "…"})

    def test_the_corpus_measures_the_seed_as_it_ships(self):
        data = etree.parse(MODULE / "data" / "speech_vocabulary_form_data.xml")
        shipped = {
            record.get("id"): tuple(
                record.findtext(f"field[@name='{name}']")
                for name in ("phrases", "word", "pronunciation")
            )
            for record in data.iter("record")
        }
        fixture = (MODULE / "static" / "tests" / "corpus" / "terms.js").read_text()
        measured = [
            tuple(json_loads(value) for value in row)
            for row in SEED_ROW.findall(fixture)
        ]
        self.assertEqual(measured, list(shipped.values()))
        for xmlid, (phrases, word, _pronunciation) in shipped.items():
            term = self.env.ref(f"voice.{xmlid}")
            self.assertEqual((term.phrases, term.word), (phrases, word))

    def test_a_chosen_reading_is_learned_and_waits_for_approval(self):
        learn = self.Term.with_user(self.user).learn
        self.assertFalse(learn("Sin pagal", "sin pagar"))
        settings = self.env["res.users.settings"]._get_or_create_for_user(self.user)
        settings.voice_share_sentences = True
        self.assertTrue(learn("Sin pagal", "sin pagar"))
        self.assertTrue(learn("sin  pagal.", "Sin pagar"))
        self.assertFalse(learn("sin pagar", "sin pagar"))
        term = self.Term.with_context(active_test=False).search(
            [("source", "=", "learned")]
        )
        self.assertRecordValues(
            term,
            [
                {
                    "phrases": "sin pagal",
                    "word": "sin pagar",
                    "active": False,
                    "confirmations": 2,
                    "company_id": self.user.company_id.id,
                }
            ],
        )
        self.assertNotIn(
            "sin pagal",
            [
                p
                for t in self.Term.with_user(self.user).spoken_terms()
                for p in t["phrases"]
            ],
        )
        with self.assertRaises(AccessError):
            term.with_user(self.user).action_approve()
        term.action_approve()
        self.assertIn(
            {"phrases": ["sin pagal"], "means": "sin pagar", "kind": "local"},
            self.Term.with_user(self.user).spoken_terms(),
        )

    def test_a_user_cannot_teach_a_term_directly(self):
        with self.assertRaises(AccessError):
            self.Term.with_user(self.user).create(
                {"phrases": "bodega", "word": "almacén", "source": "learned"}
            )
