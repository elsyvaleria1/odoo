from lxml import etree

from odoo.tests import TransactionCase, tagged

PHRASES = "finish the delivery; finish the transfer; finish the receipt"


@tagged("post_install", "-at_install")
class TestSpokenValidate(TransactionCase):
    def _validate_buttons(self, lang=None):
        picking = self.env["stock.picking"].with_context(lang=lang)
        arch = picking.get_views([(False, "form")])["views"]["form"]["arch"]
        return etree.fromstring(arch).xpath("//header/button[@name='button_validate']")

    def test_both_validate_buttons_answer_to_their_phrases(self):
        buttons = self._validate_buttons()
        self.assertEqual(len(buttons), 2)
        self.assertEqual({button.get("spoken") for button in buttons}, {PHRASES})
        self.assertEqual({button.get("string") for button in buttons}, {"Validate"})

    def test_the_phrases_are_spoken_in_the_users_language(self):
        self.env["res.lang"]._activate_lang("es_MX")
        self.env["ir.module.module"]._load_module_terms(["stock_voice"], ["es_MX"])
        spoken = {button.get("spoken") for button in self._validate_buttons("es_MX")}
        self.assertEqual(
            spoken, {"termina la entrega; termina el traslado; termina la recepción"}
        )
