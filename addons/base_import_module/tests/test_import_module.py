import base64
import threading
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import odoo.tests
from odoo import release
from odoo.exceptions import UserError
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads
from odoo.libs.worker_thread import is_running_module_operation
from odoo.tests import new_test_user
from odoo.tools import file_open, file_open_temporary_directory, mute_logger
from odoo.tools.files import file_open_temporary_paths
from odoo.tools.translate import TranslationModuleReader

from odoo.addons import __path__ as __addons_path__


@odoo.tests.tagged("post_install", "-at_install")
class TestImportModule(odoo.tests.TransactionCase):
    def setUp(self):
        super().setUp()
        # An import commits when it releases the module-operations lock, as
        # every module operation does; the test's own rollback still undoes it.
        self.startPatcher(patch.object(self.env.cr, "commit", self.env.cr.flush))

    def manifest_content(self, manifest=None, /, **values):
        return json_dumps_bytes(
            {
                "author": "Odoo S.A.",
                "license": "LGPL-3",
                **(manifest or {}),
                **values,
            }
        )

    def archive(self, files):
        archive = BytesIO()
        with ZipFile(archive, "w") as zipf:
            for path, data in files:
                zipf.writestr(path, data)
        return archive

    def import_zipfile(self, files):
        return self.env["ir.module.module"]._import_zipfile(self.archive(files))

    def _spy_module_operation(self, method_name, marks):
        IrModule = type(self.env["ir.module.module"])
        origin = getattr(IrModule, method_name)

        def spy(self, *args, **kwargs):
            marks.append(
                (method_name, is_running_module_operation(threading.current_thread()))
            )
            return origin(self, *args, **kwargs)

        return patch.object(IrModule, method_name, spy)

    def test_the_whole_import_runs_as_a_module_operation(self):
        marks = []
        with (
            self._spy_module_operation("_load_imported_data_files", marks),
            self._spy_module_operation("_render_welcome_article", marks),
        ):
            self.import_zipfile([("foo/__manifest__.py", self.manifest_content())])
        self.assertEqual(
            marks,
            [("_load_imported_data_files", True), ("_render_welcome_article", True)],
            "the data files of an import loaded on limit_time_real, so a cancel "
            "left the dependencies installed and the module not",
        )

    def test_a_dependency_install_reenters_the_import_operation(self):
        dependency = self.env["ir.module.module"].search(
            [("state", "=", "uninstalled")], limit=1
        )
        IrModule = type(self.env["ir.module.module"])
        installed = []

        def button_immediate_install(self):
            with self._lock_against_concurrent_module_operations():
                installed.append(
                    (
                        self.name,
                        is_running_module_operation(threading.current_thread()),
                    )
                )

        with patch.object(
            IrModule, "button_immediate_install", button_immediate_install
        ):
            self.import_zipfile(
                [
                    (
                        "foo/__manifest__.py",
                        self.manifest_content(depends=["base", dependency.name]),
                    )
                ]
            )
        self.assertEqual(installed, [(dependency.name, True)])

    def test_an_uploaded_sql_data_file_is_not_executed(self):
        self.import_zipfile(
            [
                ("foo/__manifest__.py", self.manifest_content(data=["data.sql"])),
                (
                    "foo/data.sql",
                    (
                        b"INSERT INTO res_currency (name, symbol, active) "
                        b"VALUES ('New Currency', 'NCU', TRUE);"
                    ),
                ),
            ]
        )
        self.assertEqual(
            self.env["res.currency"].search_count([("symbol", "=", "NCU")]), 0
        )

    def test_import_zip(self):
        files = [
            (
                "foo/__manifest__.py",
                self.manifest_content(data=["data.xml", "res.partner.csv"]),
            ),
            (
                "foo/data.xml",
                b"""
                <data>
                    <record id="foo" model="res.partner">
                        <field name="name">foo</field>
                    </record>
                </data>
            """,
            ),
            ("foo/res.partner.csv", b'"id","name"\nbar,bar'),
            ("foo/static/src/css/style.css", b".foo{color: black;}"),
            ("foo/static/src/js/foo.js", b"console.log('foo')"),
            ("bar/__manifest__.py", self.manifest_content(data=["data.xml"])),
            ("bar/static/src/js/bar.js", b"console.log(_t('baz')"),
            (
                "bar/data.xml",
                b"""
                <data>
                    <record id="foo" model="res.country">
                        <field name="name">foo</field>
                        <field name="code">XX</field>
                    </record>
                </data>
            """,
            ),
            (
                "bar/i18n/fr.po",
                b"""
                #. module: bar
                #: model:res.country,name:bar.foo
                msgid "foo"
                msgstr "dumb"

                #. module: bar
                #. odoo-javascript
                #: code:addons/foo/static/src/js/foo.js:0
                msgid "baz"
                msgstr "qux"
            """,
            ),
            (
                "bar/i18n/nl.po",
                b"""
                #. module: bar
                #: model:res.country,name:bar.foo
                msgid "foo"
                msgstr "dumb_nl"

                #. module: bar
                #. odoo-javascript
                #: code:addons/foo/static/src/js/baz.js:0
                msgid "baz"
                msgstr "qux_nl"
            """,
            ),
        ]
        self.env["res.lang"]._activate_lang("fr_FR")
        with self.assertLogs(
            "odoo.addons.base_import_module.models.ir_module"
        ) as log_catcher:
            self.import_zipfile(files)
            self.assertIn(
                "INFO:odoo.addons.base_import_module.models.ir_module:module foo: no translation for language fr_FR",
                log_catcher.output,
            )
        self.assertEqual(self.env.ref("foo.foo")._name, "res.partner")
        self.assertEqual(self.env.ref("foo.foo").name, "foo")
        self.assertEqual(self.env.ref("foo.bar")._name, "res.partner")
        self.assertEqual(self.env.ref("foo.bar").name, "bar")

        self.assertEqual(self.env.ref("bar.foo")._name, "res.country")
        self.assertEqual(self.env.ref("bar.foo").name, "foo")
        self.assertEqual(
            self.env.ref("bar.foo").with_context(lang="fr_FR").name, "dumb"
        )

        self.env["res.lang"]._activate_lang("es_419")
        self.assertEqual(
            self.env.ref("bar.foo").with_context(lang="es_419").name, "foo"
        )

        for path, data in files:
            if path.split("/")[1] == "static":
                static_attachment = self.env["ir.attachment"].search(
                    [("url", "=", "/%s" % path)]
                )
                self.assertEqual(static_attachment.name, Path(path).name)
                self.assertEqual(static_attachment.datas, base64.b64encode(data))

        self.assertEqual(
            self.env["ir.http"]._get_translations_for_webclient(["bar"], "fr_FR")[0][
                "bar"
            ],
            {"messages": ({"id": "baz", "string": "qux"},)},
        )

        self.env["res.lang"]._activate_lang("nl_NL")
        self.assertEqual(
            self.env["ir.http"]._get_translations_for_webclient(["bar"], "nl_NL")[0][
                "bar"
            ],
            {"messages": ({"id": "baz", "string": "qux_nl"},)},
        )
        self.assertEqual(self.env.ref("bar.foo").with_context(lang="nl_NL").name, "foo")
        self.env["ir.module.module"].search(
            [("name", "=", "bar")]
        )._update_translations("nl_NL")
        self.assertEqual(
            self.env.ref("bar.foo").with_context(lang="nl_NL").name, "dumb_nl"
        )

        po_reader = TranslationModuleReader(self.env.cr, ["bar"], "fr_FR")
        self.assertEqual(
            po_reader._to_translate,
            [
                (
                    "bar",
                    "foo",
                    "res.country,name",
                    "bar.foo",
                    "model",
                    (),
                    "dumb",
                ),
                (
                    "bar",
                    "baz",
                    r"addons/bar/static/src/js/bar.js",
                    1,
                    "code",
                    ("odoo-javascript",),
                    "qux",
                ),
            ],
        )

    def test_a_module_missing_a_language_is_reported_after_one_that_has_it(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.import_zipfile(
            [
                ("with_fr/__manifest__.py", self.manifest_content(data=["data.xml"])),
                (
                    "with_fr/data.xml",
                    b"""<data>
                        <record id="farming" model="res.partner.industry">
                            <field name="name">Farming</field>
                        </record>
                    </data>""",
                ),
                (
                    "with_fr/i18n/fr.po",
                    b"""
                    #. module: with_fr
                    #: model:res.partner.industry,name:with_fr.farming
                    msgid "Farming"
                    msgstr "Agriculture"
                """,
                ),
                (
                    "without_fr/__manifest__.py",
                    self.manifest_content(data=["data.xml"]),
                ),
                (
                    "without_fr/data.xml",
                    b"""<data>
                        <record id="mining" model="res.partner.industry">
                            <field name="name">Mining</field>
                        </record>
                    </data>""",
                ),
            ]
        )
        with self.assertLogs(
            "odoo.addons.base_import_module.models.ir_module", "INFO"
        ) as logs:
            self.env["ir.module.module"]._load_module_terms(
                ["with_fr", "without_fr"], ["fr_FR"]
            )
        missing = [
            line.split(":", 2)[2]
            for line in logs.output
            if "no translation for language" in line
        ]
        self.assertEqual(
            missing, ["module without_fr: no translation for language fr_FR"]
        )

    def test_a_module_translating_only_code_terms_is_not_reported_missing(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.import_zipfile(
            [
                ("code_fr/__manifest__.py", self.manifest_content()),
                (
                    "code_fr/i18n/fr.po",
                    b"""
                    #. module: code_fr
                    #. odoo-javascript
                    #: code:addons/code_fr/static/src/app.js:0
                    msgid "Farming"
                    msgstr "Agriculture"
                """,
                ),
                ("without_fr/__manifest__.py", self.manifest_content()),
            ]
        )
        with self.assertLogs(
            "odoo.addons.base_import_module.models.ir_module", "INFO"
        ) as logs:
            self.env["ir.module.module"]._load_module_terms(
                ["code_fr", "without_fr"], ["fr_FR"]
            )
        missing = [
            line.split(":", 2)[2]
            for line in logs.output
            if "no translation for language" in line
        ]
        self.assertEqual(
            missing, ["module without_fr: no translation for language fr_FR"]
        )

    def test_import_zip_invalid_manifest(self):
        files = [("foo/__manifest__.py", b"foo")]
        error_message = "Error while importing module 'foo'"
        with (
            mute_logger("odoo.addons.base_import_module.models.ir_module"),
            self.assertRaises(UserError, msg=error_message),
        ):
            self.import_zipfile(files)

    def test_import_zip_wildcard_assets(self):
        files = [
            (
                "foo/__manifest__.py",
                self.manifest_content(
                    assets={"web.assets_backend": ["test_module/static/src/js/*"]}
                ),
            ),
            ("foo/static/js/foo.js", b"console.log('foo')"),
        ]
        with (
            mute_logger("odoo.addons.base_import_module.models.ir_module"),
            self.assertRaises(
                UserError,
                msg="modules with assets path containing glob wildcards shouldn't be successcully imported",
            ),
        ):
            self.import_zipfile(files)

    def test_import_zip_malformed_xml_asset_does_not_abort_import(self):
        files = [
            ("foo/__manifest__.py", self.manifest_content()),
            ("foo/static/src/xml/broken.xml", b"<not><valid</not>"),
        ]
        self.import_zipfile(files)
        module = self.env["ir.module.module"].search([("name", "=", "foo")])
        self.assertEqual(module.state, "installed")

    def test_import_zip_invalid_data(self):
        files = [
            ("foo/__manifest__.py", self.manifest_content(data=["foo.xml", "bar.xml"])),
            (
                "foo/foo.xml",
                b"""
                <data>
                    <record id="foo" model="res.partner">
                        <field name="name">foo</field>
                    </record>
                </data>
            """,
            ),
            (
                "foo/bar.xml",
                b"""
                <data>
                    <record id="bar" model="res.prtner">
                        <field name="name">bar</field>
                    </record>
                </data>
            """,
            ),
        ]
        with (
            mute_logger("odoo.addons.base_import_module.models.ir_module"),
            self.assertRaises(UserError),
        ):
            self.import_zipfile(files)
        self.assertFalse(self.env.ref("foo.foo", raise_if_not_found=False))

    def test_import_zip_data_not_in_manifest(self):
        files = [
            ("foo/__manifest__.py", self.manifest_content(data=["foo.xml"])),
            (
                "foo/foo.xml",
                b"""
                <data>
                    <record id="foo" model="res.partner">
                        <field name="name">foo</field>
                    </record>
                </data>
            """,
            ),
            (
                "foo/bar.xml",
                b"""
                <data>
                    <record id="bar" model="res.partner">
                        <field name="name">bar</field>
                    </record>
                </data>
            """,
            ),
        ]
        self.import_zipfile(files)
        self.assertEqual(self.env.ref("foo.foo").name, "foo")
        self.assertFalse(self.env.ref("foo.bar", raise_if_not_found=False))

    def test_import_zip_ignore_unexpected_data_extension(self):
        files = [
            ("foo/__manifest__.py", self.manifest_content(data=["res.partner.xls"])),
            ("foo/res.partner.xls", b'"id","name"\nfoo,foo'),
        ]
        with self.assertLogs(
            "odoo.addons.base_import_module.models.ir_module"
        ) as log_catcher:
            self.import_zipfile(files)
            self.assertIn(
                "INFO:odoo.addons.base_import_module.models.ir_module:module foo: skip unsupported file res.partner.xls",
                log_catcher.output,
            )
            self.assertIn(
                "INFO:odoo.addons.base_import_module.models.ir_module:Successfully imported module 'foo'",
                log_catcher.output,
            )
            self.assertFalse(self.env.ref("foo.foo", raise_if_not_found=False))

    def test_import_zip_extract_only_useful(self):
        files = [
            (
                "foo/__manifest__.py",
                self.manifest_content(data=["data.xml", "res.partner.xls"]),
            ),
            (
                "foo/data.xml",
                b"""
                <data>
                    <record id="foo" model="res.partner">
                        <field name="name">foo</field>
                    </record>
                </data>
            """,
            ),
            ("foo/res.partner.xls", b'"id","name"\nfoo,foo'),
            ("foo/static/css/style.css", b".foo{color: black;}"),
            ("foo/foo.py", b"foo = 42"),
        ]
        extracted_files = []
        addons_path = []
        origin_import_module = type(self.env["ir.module.module"])._import_module

        def _import_module(self, *args, **kwargs):
            _module, path = args
            for root, _dirs, files in Path(path).walk():
                extracted_files.extend(
                    str((root / file).relative_to(path)) for file in files
                )
            addons_path.extend(__addons_path__)
            return origin_import_module(self, *args, **kwargs)

        with patch.object(
            type(self.env["ir.module.module"]), "_import_module", _import_module
        ):
            self.import_zipfile(files)
        self.assertIn(
            "__manifest__.py",
            extracted_files,
            "__manifest__.py must be in the extracted files",
        )
        self.assertIn(
            "data.xml",
            extracted_files,
            "data.xml must be in the extracted files as its in the manifest's data",
        )
        self.assertIn(
            "static/css/style.css",
            extracted_files,
            "style.css must be in the extracted files as its in the static folder",
        )
        self.assertNotIn(
            "res.partner.xls",
            extracted_files,
            "res.partner.xls must not be in the extracted files as it uses an unsupported extension of data file",
        )
        self.assertNotIn(
            "foo.py",
            extracted_files,
            "foo.py must not be in the extracted files as its not the manifest's data",
        )
        self.assertFalse(
            set(addons_path).difference(__addons_path__),
            "No directory must be added in the addons path during import",
        )

    def test_import_zip_cumulative_size_cap(self):
        files = [
            ("foo/__manifest__.py", self.manifest_content(data=["data.xml"])),
            (
                "foo/data.xml",
                b"""
                <data>
                    <record id="foo" model="res.partner">
                        <field name="name">foo</field>
                    </record>
                </data>
            """,
            ),
        ]
        with patch(
            "odoo.addons.base_import_module.models.ir_module.MAX_TOTAL_EXTRACTED_SIZE",
            10,
        ):
            with self.assertRaises(UserError):
                self.import_zipfile(files)

    def test_import_zip_per_file_size_cap(self):
        files = [("foo/__manifest__.py", self.manifest_content(data=["data.xml"]))]
        with patch(
            "odoo.addons.base_import_module.models.ir_module.MAX_FILE_SIZE",
            10,
        ):
            with self.assertRaisesRegex(UserError, "exceed maximum allowed file size"):
                self.import_zipfile(files)

    def test_import_zip_static_asset_path_confined(self):
        extracted_paths = []
        original_extract = ZipFile.extract

        def spy_extract(zip_self, member, path=None, pwd=None):
            result = original_extract(zip_self, member, path, pwd)
            extracted_paths.append((path, result))
            return result

        files = [
            ("foo/__manifest__.py", self.manifest_content()),
            ("foo/static/../../../../tmp/evil.txt", b"pwned"),
        ]
        with patch.object(ZipFile, "extract", spy_extract):
            self.import_zipfile(files)

        self.assertTrue(extracted_paths, "the crafted entry should still be extracted")
        for target_dir, extracted_path in extracted_paths:
            self.assertTrue(
                Path(extracted_path)
                .resolve()
                .is_relative_to(Path(target_dir).resolve()),
                f"{extracted_path} escaped the confinement of {target_dir}",
            )

    def test_get_modules_from_apps_reapplies_local_domain(self):
        self.env["ir.module.module"].create(
            {"name": "module_a", "state": "installed", "imported": True}
        )
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "result": [
                {"name": "module_a"},
                {"name": "module_b"},
            ]
        }
        IrModuleModule = type(self.env["ir.module.module"])
        with patch.object(IrModuleModule, "_call_apps", return_value=fake_response):
            modules_list = self.env["ir.module.module"]._get_modules_from_apps(
                ["name", "state"],
                "industries",
                False,
                domain=[("state", "=", "installed")],
            )
        self.assertEqual(
            [mod["name"] for mod in modules_list],
            ["module_a"],
            "module_b (locally uninstalled) must be filtered out by the "
            "`state` domain condition, not silently returned",
        )

    def test_button_immediate_upgrade_hidden_for_imported_module(self):
        import lxml.etree

        IrModuleModule = self.env["ir.module.module"]
        kanban_arch = IrModuleModule.get_view(
            self.env.ref("base.module_view_kanban").id, "kanban"
        )["arch"]
        form_arch = IrModuleModule.get_view(
            self.env.ref("base.module_form").id, "form"
        )["arch"]
        kanban_node = lxml.etree.fromstring(kanban_arch).xpath(
            "//a[@name='button_immediate_upgrade']"
        )[0]
        form_node = lxml.etree.fromstring(form_arch).xpath(
            "//button[@name='button_immediate_upgrade']"
        )[0]
        self.assertIn(
            "imported",
            kanban_node.get("invisible") or "",
            "kanban Upgrade button must stay hidden for imported modules",
        )
        self.assertIn(
            "imported",
            form_node.get("invisible") or "",
            "form Upgrade button must stay hidden for imported modules",
        )

    def test_decorate_apps_modules_batches_search(self):
        self.env["ir.module.module"].create(
            {"name": "module_a", "state": "installed", "imported": True}
        )
        modules_list = [
            {"name": "module_a"},
            {"name": "module_b"},
            {"name": "module_c"},
        ]
        with self.assertQueryCount(default=1):
            self.env["ir.module.module"]._decorate_apps_modules(
                modules_list, ["name", "state"], "official"
            )
        self.assertEqual(modules_list[0]["state"], "installed")
        self.assertEqual(modules_list[1]["state"], "uninstalled")
        self.assertEqual(modules_list[2]["state"], "uninstalled")

    def test_import_and_uninstall_module(self):
        bundle = "web.assets_backend"
        path = "/test_module/static/src/js/test.js"
        manifest_content = self.manifest_content(
            {
                "name": "Test Module",
                "description": "Test",
                "assets": {"web.assets_backend": ["test_module/static/src/js/test.js"]},
                "category": "Test Category",
                "depends": ["base"],
            }
        )

        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("test_module/__manifest__.py", manifest_content)
            archive.writestr("test_module/static/src/js/test.js", "console.log('AAA');")

        self.env["ir.module.module"]._import_zipfile(stream)

        attachment = self.env["ir.attachment"].search([("url", "=", path)])
        self.assertEqual(attachment.name, "test.js")
        self.assertEqual(attachment.type, "binary")
        self.assertEqual(attachment.raw, b"console.log('AAA');")

        asset = self.env["ir.asset"].search(
            [("name", "=", f"test_module.{bundle}.{path}")]
        )
        self.assertEqual(asset.path, path)
        self.assertEqual(asset.bundle, bundle)
        self.assertEqual(asset.directive, "append")
        self.assertEqual(asset.target, False)

        asset_data = self.env["ir.model.data"].search(
            [("model", "=", "ir.asset"), ("res_id", "=", asset.id)]
        )
        self.assertEqual(asset_data.module, "test_module")
        self.assertEqual(asset_data.name, f"{bundle}_{path}".replace(".", "_"))

        module = self.env["ir.module.module"].search([("name", "=", "test_module")])
        self.assertEqual(module.dependencies_id.mapped("name"), ["base"])
        self.assertEqual(module.category_id.name, "Test Category")

        self.env["ir.module.module"].search(
            [("name", "=", "test_module")]
        ).module_uninstall()

        attachment = self.env["ir.attachment"].search([("url", "=", path)])
        self.assertEqual(len(attachment), 0)

        asset = self.env["ir.asset"].search(
            [("name", "=", f"test_module.{bundle}.{path}")]
        )
        self.assertEqual(len(asset), 0)

        asset_data = self.env["ir.model.data"].search(
            [("model", "=", "ir.asset"), ("res_id", "=", asset.id)]
        )
        self.assertEqual(len(asset_data), 0)

    def test_import_and_update_module(self):
        self.test_user = new_test_user(
            self.env,
            login="Admin",
            groups="base.group_user,base.group_system",
            name="Admin",
        )
        bundle = "web.assets_backend"
        path = "test_module/static/src/js/test.js"
        manifest_content = self.manifest_content(
            {
                "name": "Test Module",
                "description": "Test",
                "assets": {bundle: [path]},
                "version": "1.0",
            }
        )
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("test_module/__manifest__.py", manifest_content)
            archive.writestr(path, "console.log('AAA');")

        self.env["ir.module.module"].with_user(self.test_user)._import_zipfile(stream)

        attachment = self.env["ir.attachment"].search([("url", "=", f"/{path}")])
        self.assertEqual(attachment.name, "test.js")
        self.assertEqual(attachment.type, "binary")
        self.assertEqual(attachment.raw, b"console.log('AAA');")

        asset = self.env["ir.asset"].search(
            [("name", "=", f"test_module.{bundle}./{path}")]
        )
        self.assertEqual(asset.path, f"/{path}")
        self.assertEqual(asset.bundle, bundle)
        self.assertEqual(asset.directive, "append")
        self.assertEqual(asset.target, False)

        asset_data = self.env["ir.model.data"].search(
            [("model", "=", "ir.asset"), ("res_id", "=", asset.id)]
        )
        self.assertEqual(asset_data.module, "test_module")
        self.assertEqual(asset_data.name, f"{bundle}_/{path}".replace(".", "_"))

        module = self.env["ir.module.module"].search([("name", "=", "test_module")])
        self.assertEqual(module.db_version, f"{release.series}.1.0")

        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("test_module/__manifest__.py", manifest_content)
            archive.writestr(path, "console.log('BBB');")

        self.env["ir.module.module"].with_user(self.test_user)._import_zipfile(stream)

        attachment = self.env["ir.attachment"].search([("url", "=", f"/{path}")])
        self.assertEqual(attachment.name, "test.js")
        self.assertEqual(attachment.type, "binary")
        self.assertEqual(attachment.raw, b"console.log('BBB');")

        asset = self.env["ir.asset"].search(
            [("name", "=", f"test_module.{bundle}./{path}")]
        )
        self.assertEqual(asset.path, f"/{path}")
        self.assertEqual(asset.bundle, bundle)
        self.assertEqual(asset.directive, "append")
        self.assertEqual(asset.target, False)

        asset_data = self.env["ir.model.data"].search(
            [("model", "=", "ir.asset"), ("res_id", "=", asset.id)]
        )
        self.assertEqual(asset_data.module, "test_module")
        self.assertEqual(asset_data.name, f"{bundle}_/{path}".replace(".", "_"))

    def test_import_wrong_dependencies(self):
        files = [
            (
                "foo/__manifest__.py",
                self.manifest_content(data=["foo.xml"], depends=["base", "bar", "baz"]),
            ),
            (
                "foo/foo.xml",
                b"""
                <data>
                    <record id="foo" model="res.partner">
                        <field name="name">foo</field>
                    </record>
                </data>
            """,
            ),
        ]
        with (
            mute_logger("odoo.addons.base_import_module.models.ir_module"),
            self.assertRaisesRegex(
                UserError,
                "Unknown module dependencies",
                msg="Cannot allow import of modules with unknown dependencies",
            ),
        ):
            self.import_zipfile(files)

    def test_import_modules_with_dependencies(self):
        files = [
            (
                "baz/__manifest__.py",
                self.manifest_content(
                    data=["partner.xml"], depends=["base", "bar", "foo"]
                ),
            ),
            (
                "baz/partner.xml",
                b"""
                <data>
                    <record id="foo.baz" model="res.partner">
                        <field name="name">baz</field>
                    </record>
                </data>
            """,
            ),
            (
                "foo/__manifest__.py",
                self.manifest_content(data=["partner.xml"], depends=["base"]),
            ),
            (
                "foo/partner.xml",
                b"""
                <data>
                    <record id="baz" model="res.partner">
                        <field name="name">foo</field>
                    </record>
                </data>
            """,
            ),
            ("bar/__manifest__.py", self.manifest_content(depends=["base", "foo"])),
        ]
        self.import_zipfile(files)
        module = self.env["ir.module.module"].search([("name", "=", "baz")])
        self.assertEqual(
            set(module.dependencies_id.mapped("name")), {"bar", "base", "foo"}
        )

    def test_multiple_file_open_temporary_directory(self):
        files = [("foo/__manifest__.py", self.manifest_content(name="foo"))]
        with (
            ZipFile(self.archive(files), "r") as zip_files,
            file_open_temporary_directory() as tmp_dir,
            file_open_temporary_directory() as other_tmp_dir,
        ):
            zip_files.extract("foo/__manifest__.py", tmp_dir)
            zip_files.extract("foo/__manifest__.py", other_tmp_dir)
            self.assertEqual(
                json_loads(file_open(tmp_dir + "/foo/__manifest__.py", "r").read())[
                    "name"
                ],
                "foo",
            )
            self.assertEqual(
                json_loads(
                    file_open(other_tmp_dir + "/foo/__manifest__.py", "r").read()
                )["name"],
                "foo",
            )
            tmp_folder = tmp_dir
        self.assertFalse(file_open_temporary_paths())
        with self.assertRaises(FileNotFoundError):
            file_open(tmp_folder + "/foo/__manifest__.py", "r")

    def test_check_zip_dependencies(self):
        files = [("foo/__manifest__.py", self.manifest_content(data=["data.xml"]))]
        archive = BytesIO()
        with ZipFile(archive, "w") as zipf:
            for path, data in files:
                zipf.writestr(path, data)
        modules_dependencies, _not_found = self.env[
            "ir.module.module"
        ]._get_missing_dependencies(archive.getvalue())
        import_module = self.env["wizard.ir.module.module.import"].create(
            {
                "module_file": base64.b64encode(archive.getvalue()),
                "state": "init",
                "modules_dependencies": modules_dependencies,
            }
        )
        dependencies_names = import_module.get_dependencies_to_install_names()
        self.assertEqual(dependencies_names, [])


class TestImportModuleHttp(TestImportModule, odoo.tests.HttpCase):
    def test_login_upload_answers_403_on_bad_credentials(self):
        response = self.url_open(
            "/base_import_module/login_upload",
            data={
                "login": "admin",
                "password": "not-the-password",
                "db": self.env.cr.dbname,
            },
            files={"mod_file": ("mod.zip", b"not a zip")},
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("Access Denied", response.text)

    def test_import_module_icon(self):
        files = [
            ("foo/__manifest__.py", self.manifest_content(name="foo")),
            ("foo/static/description/icon.png", b"foo_icon"),
            ("bar/__manifest__.py", self.manifest_content(name="bar")),
        ]
        self.import_zipfile(files)
        foo_icon_path, foo_icon_data = files[1]
        self.assertEqual(self.url_open("/" + foo_icon_path).content, foo_icon_data)
        self.assertEqual(
            self.env.ref("base.module_bar").icon_image,
            self.env.ref("base.module_base").icon_image,
        )

    def test_import_module_field_file(self):
        files = [
            ("foo/__manifest__.py", self.manifest_content(data=["data.xml"])),
            (
                "foo/data.xml",
                b"""
                <data>
                    <record id="logo" model="ir.attachment">
                        <field name="name">Company Logo</field>
                        <field name="datas" type="base64" file="foo/static/src/img/content/logo.png"/>
                        <field name="res_model">ir.ui.view</field>
                        <field name="public" eval="True"/>
                    </record>
                </data>
            """,
            ),
            ("foo/static/src/img/content/logo.png", b"foo_logo"),
        ]
        self.import_zipfile(files)
        logo_path, logo_data = files[2]
        self.assertEqual(base64.b64decode(self.env.ref("foo.logo").datas), logo_data)
        self.assertEqual(self.url_open("/" + logo_path).content, logo_data)

    def test_import_module_assets_http(self):
        asset_bundle = "web_assets_backend"
        asset_path = "/foo/static/src/js/test.js"
        files = [
            (
                "foo/__manifest__.py",
                self.manifest_content(
                    assets={asset_bundle: [asset_path]},
                ),
            ),
            ("foo/static/src/js/test.js", b"foo_assets_backend"),
        ]
        self.import_zipfile(files)
        asset = self.env.ref("foo.web_assets_backend_/foo/static/src/js/test_js")
        self.assertEqual(asset.bundle, asset_bundle)
        self.assertEqual(asset.path, asset_path)
        asset_data = files[1][1]
        self.assertEqual(self.url_open(asset_path).content, asset_data)
