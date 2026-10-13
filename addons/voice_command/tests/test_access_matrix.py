from odoo import fields
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona
from odoo.addons.voice_command.tools.utterance import ENGLISH_PASS_PARAMETER


@tagged("post_install", "-at_install", "access_matrix")
class TestVoiceAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "employee_b": Persona(company="b"),
        "system_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
    }
    cells = (
        Cell(
            "voice.sentence",
            "sentence_a",
            system_a="rd",
            note="a user adds one only through voice.sentence.record",
        ),
        Cell(
            "speech.vocabulary.form",
            "term_shared",
            employee_a="r learn",
            employee_b="r learn",
            system_a="rwcd learn",
        ),
        Cell(
            "speech.vocabulary.form",
            "term_a",
            employee_a="r learn",
            system_a="rwcd learn",
        ),
        Cell(
            "speech.vocabulary.form",
            "term_b",
            employee_b="r learn",
            system_a="rwcd learn",
        ),
        Cell(
            "speech.vocabulary.form",
            "learned_a",
            employee_a="r learn",
            system_a="rwcd learn",
            note="a user adds or counts one only through speech.vocabulary.form.learn",
        ),
        Cell(
            "speech.vocabulary",
            "word_shared",
            employee_a="r",
            employee_b="r",
            system_a="rwcd",
            note="a learned form adds its word only through "
            "speech.vocabulary.form.learn",
        ),
        Cell(
            "ir.config_parameter",
            "english_pass",
            system_a="rwcd",
            note="the voice client reads it only through "
            "voice_command.privilege_read_english_pass, which no user holds",
        ),
    )

    @classmethod
    def build(cls):
        a, b = cls.companies["a"], cls.companies["b"]
        terms = cls.env["speech.vocabulary.form"]
        return {
            "word_shared": cls.env["speech.vocabulary"].create({"name": "matrix word"}),
            "english_pass": cls.env["ir.config_parameter"].create(
                {"key": ENGLISH_PASS_PARAMETER, "value": "True"}
            ),
            "sentence_a": cls.env["voice.sentence"].create(
                {
                    "day": fields.Date.today(),
                    "company_id": a.id,
                    "answered_by": "none",
                    "text": "el perro come croquetas",
                }
            ),
            "term_shared": terms.create({"phrases": "matrix shared", "word": "uno"}),
            "term_a": terms.create(
                {"phrases": "matrix a", "word": "dos", "company_id": a.id}
            ),
            "term_b": terms.create(
                {"phrases": "matrix b", "word": "tres", "company_id": b.id}
            ),
            "learned_a": terms.create(
                {
                    "phrases": "matrix learned",
                    "word": "cuatro",
                    "source": "learned",
                    "active": False,
                    "company_id": a.id,
                }
            ),
        }
