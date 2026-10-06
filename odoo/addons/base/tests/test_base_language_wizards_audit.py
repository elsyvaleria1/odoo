import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.translate import get_lang_iso_codes, get_module_po_path


@tagged("post_install", "-at_install")
class TestBaseLanguageWizardsAudit(TransactionCase):
    def _make_model_export(self, domain):
        partner_model = self.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )
        return self.env["wizard.res.lang.export.translation"].create(
            {
                "lang": "__new__",
                "format": "po",
                "export_type": "model",
                "model_id": partner_model.id,
                "domain": domain,
            }
        )

    def test_blexp1_syntax_error_domain_raises_usererror(self):
        wizard = self._make_model_export("[(1,2")
        with self.assertRaises(UserError):
            wizard.action_export_language_file()

    def test_blexp1_type_error_domain_raises_usererror(self):
        wizard = self._make_model_export("{[]:1}")
        with self.assertRaises(UserError):
            wizard.action_export_language_file()

    def test_blexp1_non_list_domain_raises_usererror(self):
        wizard = self._make_model_export("42")
        with self.assertRaises(UserError):
            wizard.action_export_language_file()

    def test_blexp_happy_path_empty_domain_produces_file(self):
        wizard = self._make_model_export("[]")
        wizard.action_export_language_file()
        self.assertEqual(wizard.state, "get")
        self.assertTrue(wizard.name)

    def test_blimp_unsupported_format_raises_usererror(self):
        admin = new_test_user(
            self.env,
            login="blimp_audit_user",
            groups="base.group_system",
        )
        wizard = (
            self.env["wizard.res.lang.import.translation"]
            .with_user(admin)
            .create(
                {
                    "name": "Test Lang",
                    "code": "xx_XX",
                    "filename": "x.txt",
                    "data": base64.b64encode(b"irrelevant content"),
                }
            )
        )
        with self.assertRaises(UserError) as cm:
            wizard.import_lang()
        self.assertIn("format mismatch", str(cm.exception))

    def test_blimp_malformed_po_is_silently_tolerated(self):
        admin = new_test_user(
            self.env,
            login="blimp_po_user",
            groups="base.group_system",
        )
        wizard = (
            self.env["wizard.res.lang.import.translation"]
            .with_user(admin)
            .create(
                {
                    "name": "Test Lang",
                    "code": "xx_XX",
                    "filename": "x.po",
                    "data": base64.b64encode(b"this is not a valid po file"),
                }
            )
        )
        self.assertTrue(wizard.import_lang())

    def _exported_file_name(self, lang):
        self.env["res.lang"]._activate_lang(lang)
        wizard = self.env["wizard.res.lang.export.translation"].create(
            {
                "lang": lang,
                "format": "po",
                "modules": [(6, 0, self.env.ref("base.module_base").ids)],
            }
        )
        wizard.action_export_language_file()
        return wizard.name

    def test_blexp_po_is_named_after_the_file_the_module_loads(self):
        iso_codes = get_lang_iso_codes(self.env)
        langs = ("sv_SE", "ja_JP", "da_DK", "pt_BR", "es_MX", "fr_FR")
        self.assertEqual(
            {lang: self._exported_file_name(lang) for lang in langs},
            {lang: get_module_po_path("base", lang, iso_codes).name for lang in langs},
        )
        self.assertEqual(self._exported_file_name("sv_SE"), "sv.po")
