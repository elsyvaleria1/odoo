import base64
import io
import tarfile

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger
from odoo.tools.translate import get_lang_iso_codes, get_module_po_path


@tagged("post_install", "-at_install")
class TestBaseLanguageWizardsAudit(TransactionCase):
    def _create_model_export_wizard(self, domain):
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
        wizard = self._create_model_export_wizard("[(1,2")
        with self.assertRaises(UserError):
            wizard.action_export_language_file()

    def test_blexp1_type_error_domain_raises_usererror(self):
        wizard = self._create_model_export_wizard("{[]:1}")
        with self.assertRaises(UserError):
            wizard.action_export_language_file()

    def test_blexp1_non_list_domain_raises_usererror(self):
        wizard = self._create_model_export_wizard("42")
        with self.assertRaises(UserError):
            wizard.action_export_language_file()

    def test_blexp_happy_path_empty_domain_produces_file(self):
        wizard = self._create_model_export_wizard("[]")
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

    def test_blimp_malformed_po_raises_usererror(self):
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
        with (
            mute_logger("odoo.addons.base.wizards.wizard_res_lang_import_translation"),
            self.assertRaises(UserError) as cm,
        ):
            wizard.import_lang()
        self.assertIn("malformed", str(cm.exception))

    def test_blimp_overwrite_replaces_a_noupdate_term(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        belgium = self.env.ref("base.be")
        belgium.with_context(lang="fr_FR").name = "Belgique existante"
        self.env.flush_all()
        self.assertTrue(
            self.env["ir.model.data"]
            .search([("module", "=", "base"), ("name", "=", "be")])
            .noupdate
        )
        po = (
            "#. module: base\n#: model:res.country,name:base.be\n"
            'msgid "Belgium"\nmsgstr "Belgique importée"\n'
        ).encode()
        self.env["wizard.res.lang.import.translation"].create(
            {
                "name": "French",
                "code": "fr_FR",
                "filename": "fr.po",
                "data": base64.b64encode(po),
                "overwrite": True,
            }
        ).import_lang()
        self.assertEqual(belgium.with_context(lang="fr_FR").name, "Belgique importée")

    def test_blexp_module_mode_is_offered_to_those_who_can_read_modules(self):
        Wizard = self.env["wizard.res.lang.export.translation"]
        user = new_test_user(self.env, login="blexp_mode", groups="base.group_user")
        admin = new_test_user(self.env, login="blexp_admin", groups="base.group_system")
        self.assertEqual(
            Wizard.with_user(user).default_get(["export_type"])["export_type"], "model"
        )
        self.assertEqual(
            Wizard.with_user(admin).default_get(["export_type"])["export_type"],
            "module",
        )

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

    def _export(self, user=None, **vals):
        wizard = self.env["wizard.res.lang.export.translation"]
        if user:
            wizard = wizard.with_user(user)
        wizard = wizard.create(vals)
        wizard.action_export_language_file()
        return wizard

    def _country_export(self, lang, file_format, user=None):
        return self._export(
            user,
            lang=lang,
            format=file_format,
            export_type="model",
            model_id=self.env["ir.model"]._get_id("res.country"),
            domain="[('code', '=', 'BE')]",
        )

    def _tar_members(self, wizard):
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(wizard.data))) as tar:
            return {
                member.name: tar.extractfile(member).read().decode()
                for member in tar.getmembers()
            }

    def test_blexp_tgz_template_exports_pot_files(self):
        module_export = self._export(
            lang="__new__",
            format="tgz",
            modules=[(6, 0, self.env.ref("base.module_base").ids)],
        )
        self.assertEqual(list(self._tar_members(module_export)), ["base/i18n/base.pot"])
        record_export = self._country_export("__new__", "tgz")
        self.assertIn("Belgium", self._tar_members(record_export)["base/i18n/base.pot"])

    def test_blexp_tgz_record_export_holds_only_the_selected_records(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        po_file = base64.b64decode(self._country_export("fr_FR", "po").data).decode()
        [tgz_file] = self._tar_members(self._country_export("fr_FR", "tgz")).values()
        self.assertIn('msgid "Belgium"', tgz_file)
        self.assertNotIn("#~ msgid", tgz_file)
        self.assertEqual(tgz_file.count("msgid"), po_file.count("msgid"))

    def test_blexp_internal_user_exports_records_they_read(self):
        user = new_test_user(self.env, login="blexp_user", groups="base.group_user")
        wizard = self._country_export("__new__", "po", user=user)
        self.assertEqual(wizard.state, "get")
        self.assertEqual(wizard.name, "res_country.pot")
        self.assertIn('msgid "Belgium"', base64.b64decode(wizard.data).decode())
