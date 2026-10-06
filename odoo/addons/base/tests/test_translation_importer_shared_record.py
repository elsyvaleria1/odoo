import io

from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL
from odoo.tools.translate import TranslationImporter

PO = """msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"

#. module: {module}
#: model:res.partner.industry,name:{module}.{name}
msgid "Farming"
msgstr "{value}"
"""

TERMS_PO = """msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"

#. module: {module}
#: model_terms:ir.ui.view,arch_db:{module}.{name}
msgid "Farming"
msgstr "{value}"
"""


@tagged("post_install", "-at_install")
class TestTranslationImporterSharedRecord(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for code in ("fr_FR", "de_DE"):
            cls.env["res.lang"]._activate_lang(code)

    def _industry_named_by(self, name, modules):
        industry = self.env["res.partner.industry"].create({"name": "Farming"})
        self.env["ir.model.data"].create(
            [
                {
                    "module": module,
                    "name": name,
                    "model": industry._name,
                    "res_id": industry.id,
                }
                for module in modules
            ]
        )
        self.env.flush_all()
        return industry

    def _import(self, name, loads):
        importer = TranslationImporter(self.env.cr, verbose=False)
        for module, lang, value in loads:
            po = PO.format(module=module, name=name, value=value)
            importer.load(io.BytesIO(po.encode()), "po", lang)
        importer.save()

    def _stored_name(self, industry):
        self.env.cr.execute(
            SQL("SELECT name FROM res_partner_industry WHERE id = %s", industry.id)
        )
        return self.env.cr.fetchone()[0]

    def _assert_merged(self, loads, expected):
        for index, xmlid_order in enumerate([("trn_a", "trn_b"), ("trn_b", "trn_a")]):
            with self.subTest(xmlid_order=xmlid_order):
                name = f"shared_industry_{index}"
                industry = self._industry_named_by(name, xmlid_order)
                self._import(name, loads)
                stored = self._stored_name(industry)
                self.assertEqual(
                    {lang: stored.get(lang) for lang in expected}, expected
                )

    def test_a_language_only_the_later_module_carries_is_kept(self):
        self._assert_merged(
            [
                ("trn_a", "fr_FR", "A-fr"),
                ("trn_b", "fr_FR", "B-fr"),
                ("trn_b", "de_DE", "B-de"),
            ],
            {"fr_FR": "B-fr", "de_DE": "B-de"},
        )

    def test_a_language_only_the_earlier_module_carries_is_kept(self):
        self._assert_merged(
            [
                ("trn_a", "fr_FR", "A-fr"),
                ("trn_a", "de_DE", "A-de"),
                ("trn_b", "fr_FR", "B-fr"),
            ],
            {"fr_FR": "B-fr", "de_DE": "A-de"},
        )

    def test_a_noupdate_xmlid_keeps_the_record_translation_on_overwrite(self):
        for index, noupdate_module in enumerate(("trn_a", "trn_b")):
            with self.subTest(noupdate_module=noupdate_module):
                name = f"noupdate_industry_{index}"
                industry = self._industry_named_by(name, ("trn_a", "trn_b"))
                industry.with_context(lang="fr_FR").name = "Kept"
                self.env["ir.model.data"].search(
                    [("module", "=", noupdate_module), ("name", "=", name)]
                ).noupdate = True
                self.env.flush_all()
                importer = TranslationImporter(self.env.cr, verbose=False)
                for module in ("trn_a", "trn_b"):
                    po = PO.format(module=module, name=name, value=f"{module}-fr")
                    importer.load(io.BytesIO(po.encode()), "po", "fr_FR")
                importer.save(overwrite=True)
                self.assertEqual(self._stored_name(industry).get("fr_FR"), "Kept")

    def test_the_module_loaded_last_wins_a_term_of_a_shared_record(self):
        for index, load_order in enumerate([("trn_a", "trn_b"), ("trn_b", "trn_a")]):
            with self.subTest(load_order=load_order):
                name = f"shared_view_{index}"
                view = self.env["ir.ui.view"].create(
                    {
                        "name": name,
                        "type": "qweb",
                        "arch": f"<t t-name='{name}'><p>Farming</p></t>",
                    }
                )
                self.env["ir.model.data"].create(
                    [
                        {
                            "module": module,
                            "name": name,
                            "model": view._name,
                            "res_id": view.id,
                        }
                        for module in ("trn_a", "trn_b")
                    ]
                )
                self.env.flush_all()
                importer = TranslationImporter(self.env.cr, verbose=False)
                for module in load_order:
                    po = TERMS_PO.format(module=module, name=name, value=f"{module}-fr")
                    importer.load(io.BytesIO(po.encode()), "po", "fr_FR")
                importer.save()
                view.invalidate_recordset(["arch_db"])
                self.assertIn(
                    f"{load_order[-1]}-fr", view.with_context(lang="fr_FR").arch_db
                )
