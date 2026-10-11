import re
import shutil
from pathlib import Path
from unittest.mock import patch

import odoo
from odoo.libs.json import dumps as json_dumps
from odoo.tests.common import HttpCase, TransactionCase, tagged
from odoo.tests.utils import InfrastructureUnavailable
from odoo.tools.assets.owl_precompile import (
    InlineSource,
    precompile_templates,
    precompiler_missing,
    web_static_path,
)

BUNDLE = "web.assets_web"
FRONTEND_BUNDLE = "web.assets_frontend_lazy"


def require_precompiler():
    node_modules = Path(odoo.__path__[0]).parent / "node_modules"
    if not shutil.which("node") or not (node_modules / "jsdom").is_dir():
        raise InfrastructureUnavailable("node with the jsdom package is unavailable")


class PrecompiledTemplatesMixin:
    def _pipeline(self, bundle=BUNDLE, **params):
        return self.env["ir.qweb"]._get_asset_bundle(bundle, css=False, **params)._xml

    def _translations_hash(self, lang):
        IrHttp = self.env["ir.http"]
        modules = IrHttp._get_webclient_translation_modules()[0]
        return IrHttp._get_web_translations_hash(modules, lang)

    def _precompiled(self, lang="en_US", env=None, dev=False):
        return (env or self.env)[
            "ir.qweb"
        ]._get_or_create_precompiled_template_attachment(
            BUNDLE,
            self._pipeline().precompile_checksum(),
            lang,
            self._translations_hash(lang),
            dev=dev,
        )


@tagged("web_unit", "web_assets")
class TestPrecompiledTemplates(PrecompiledTemplatesMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        require_precompiler()

    def test_a_bundle_announces_its_precompilable_templates(self):
        pipeline = self._pipeline()
        checksum = pipeline.precompile_checksum()
        self.assertRegex(checksum, r"^[0-9a-f]{16}$")
        self.assertIn(
            f'registerTemplateBundle("{BUNDLE}", "{checksum}", {{}}, () => {{\n',
            pipeline.generate_esm_template_bundle(use_import=False),
        )

    def test_a_compile_pregeneration_lost_is_not_retried_by_the_next_request(self):
        module = "odoo.addons.base.models.ir_qweb_assets_precompile"
        IrQweb = self.env["ir.qweb"]
        self.env["ir.attachment"]._search_generated_assets(
            url_pattern="/web/assets/owl/%"
        ).unlink()
        checksum = self._pipeline(FRONTEND_BUNDLE).precompile_checksum()
        with (
            patch.dict(f"{module}._failed_at", clear=True),
            patch.dict(f"{module}._recent_scripts", clear=True),
        ):
            with patch(f"{module}.precompile_templates", return_value=None):
                self.assertEqual(IrQweb._pregenerate_precompiled_templates(), [])
            with patch(f"{module}.precompile_templates") as precompile:
                for translations_hash in IrQweb._get_translations_hashes("en_US"):
                    self.assertFalse(
                        IrQweb._get_or_create_precompiled_template_attachment(
                            FRONTEND_BUNDLE, checksum, "en_US", translations_hash
                        )
                    )
            precompile.assert_not_called()

    def test_the_document_is_told_the_artifact_the_page_will_ask_for(self):
        IrQweb = self.env["ir.qweb"]
        with odoo.tools.config.patch(test_enable=False):
            url = IrQweb._get_page_templates_url(BUNDLE, "en_US")
            in_debug = IrQweb._get_page_templates_url(BUNDLE, "en_US", "1")
            without_a_language = IrQweb._get_page_templates_url(BUNDLE, None)
        self.assertEqual(
            url,
            IrQweb._get_precompiled_templates_url(
                BUNDLE,
                self._pipeline().precompile_checksum(),
                "en_US",
                self._translations_hash("en_US"),
            ),
        )
        self.assertIsNone(in_debug, "a page in debug compiles its templates itself")
        self.assertIsNone(without_a_language)
        self.assertIsNone(
            IrQweb._get_page_templates_url(BUNDLE, "en_US"),
            "a page under test compiles its templates itself",
        )

    def test_a_bundle_asked_under_a_query_string_is_not_named(self):
        IrQweb = self.env["ir.qweb"]
        AssetsBundle = type(IrQweb._get_asset_bundle(BUNDLE, css=False))
        with (
            odoo.tools.config.patch(test_enable=False),
            patch.object(AssetsBundle, "js_rebuild_params", {"website_id": 1}),
        ):
            self.env.registry.clear_cache("assets")
            self.addCleanup(self.env.registry.clear_cache, "assets")
            self.assertIsNone(IrQweb._get_page_templates_url(BUNDLE, "en_US"))

    def test_debug_assets_keep_compiling_in_the_browser(self):
        pipeline = self._pipeline(debug_assets=True)
        self.assertIsNone(pipeline.precompile_checksum())
        self.assertNotIn(
            "registerTemplateBundle(",
            pipeline.generate_esm_template_bundle(use_import=True),
        )

    def test_the_artifact_compiles_every_template_of_the_bundle(self):
        attachment = self._precompiled()
        self.assertTrue(attachment)
        script = attachment.raw.decode()
        self.assertTrue(
            script.startswith(
                'odoo.loader.modules.get("@web/core/templates")'
                ".registerCompiledTemplates({"
            )
        )
        names = {
            element.get("t-name")
            for block in self._pipeline().xml()
            if block["type"] == "templates"
            for element, _url, _parent in block["templates"]
        }
        self.assertGreater(len(names), 100)
        for name in names:
            self.assertIn(f"{json_dumps(name)}: [", script, name)

    def test_every_template_of_the_bundle_compiles(self):
        result = precompile_templates(
            self._pipeline().generate_xml_bundle(),
            {},
            web_static=web_static_path(),
            label=BUNDLE,
        )
        self.assertEqual(result.failures, {})

    def test_every_inline_template_of_the_bundles_compiles(self):
        for bundle in (BUNDLE, FRONTEND_BUNDLE):
            with self.subTest(bundle=bundle):
                pipeline = self._pipeline(bundle)
                sources = pipeline.inline_template_sources()
                self.assertIn(
                    "/web/static/src/ui/main_components_container.js",
                    [source.url for source in sources],
                )
                result = precompile_templates(
                    pipeline.generate_xml_bundle(),
                    {},
                    web_static=web_static_path(),
                    label=bundle,
                    sources=sources,
                )
                self.assertEqual(result.failures, {})
                self.assertGreater(result.inline, 10)

    def test_an_inline_template_is_compiled_under_its_content_key(self):
        sources = [
            InlineSource(
                "/pc/static/src/a.js",
                'import { xml } from "@odoo/owl";\n'
                "const a = xml`<p>a</p>`;\n"
                "const b = owl.xml`<p>b</p>`;\n"
                "const dynamic = xml`<p>${a}</p>`;\n"
                "const text = `<p>not a template</p>`;\n",
            ),
            InlineSource("/pc/static/src/b.js", "const again = xml`<p>a</p>`;"),
        ]
        owl_only = precompile_templates(
            "", {}, web_static=web_static_path(), label="pc"
        )
        result = precompile_templates(
            "", {}, web_static=web_static_path(), label="pc", sources=sources
        )
        self.assertEqual(result.failures, {})
        self.assertGreater(owl_only.inline, 0, "OWL's own ErrorBoundary and Suspense")
        self.assertEqual(result.inline, owl_only.inline + 2)
        self.assertIn('\n"8-', result.script)
        self.assertTrue(result.script.rstrip().endswith("}, { dev: false });"))

    def test_a_bundle_loaded_into_a_page_is_compiled_after_each_page(self):
        shared = '`<div t-name="pc.Shared" class="shared"/>`'
        extending_page = (
            f'registerTemplate("pc.Shared", "/pc/a.xml", {shared});\n'
            'registerTemplate("pc.PageOnly", "/pc/a.xml", `<i t-name="pc.PageOnly"/>`);\n'
            'registerTemplateExtension("pc.Shared", "/pc/page.xml", '
            '`<t t-inherit="pc.Shared" t-inherit-mode="extension">'
            '<xpath expr="//div" position="inside"><span class="from_page"/></xpath></t>`);'
        )
        plain_page = f'registerTemplate("pc.Shared", "/pc/a.xml", {shared});'
        pages = [extending_page, plain_page]
        child = (
            f'registerTemplate("pc.Shared", "/pc/a.xml", {shared});\n'
            'registerTemplateExtension("pc.Shared", "/pc/child.xml", '
            '`<t t-inherit="pc.Shared" t-inherit-mode="extension">'
            '<xpath expr="//div" position="inside"><b class="from_child"/></xpath></t>`);'
        )
        result = precompile_templates(
            child,
            {},
            web_static=web_static_path(),
            label="pc",
            page_registrations=pages,
        )
        self.assertEqual(result.failures, {})
        self.assertEqual(result.compiled, 2)
        self.assertEqual(result.script.count(".registerCompiledTemplates({"), 2)
        self.assertIn('<span class="from_page"/><b class="from_child"/>', result.script)
        self.assertNotIn("pc.PageOnly", result.script)

    def test_a_dynamic_child_replays_each_parent_it_can_load_into(self):
        emoji = self._pipeline("web.assets_emoji")
        parents = self.env["ir.qweb"]._get_runtime_group_parents("web.assets_emoji")
        self.assertIn("web.assets_web", parents)
        self.assertIn("web.assets_frontend", parents)
        self.assertEqual(len(emoji.page_registrations()), len(parents))
        self.assertEqual(self._pipeline().page_registrations(), [])

    def test_pregeneration_compiles_what_an_eval_free_page_awaits(self):
        IrQweb = self.env["ir.qweb"]
        IrQweb._pregenerate_assets_bundles()
        translations_hash = self._translations_hash("en_US")
        bundles = [FRONTEND_BUNDLE]
        if self.env["ir.module.module"]._get("web_tour").state == "installed":
            bundles.append("web_tour.automatic")
        for bundle in bundles:
            checksum = self._pipeline(bundle).precompile_checksum()
            self.assertIsNotNone(checksum, bundle)
            for dev in (False, True):
                with self.subTest(bundle=bundle, dev=dev):
                    self.assertTrue(
                        IrQweb._get_or_create_precompiled_template_attachment(
                            bundle,
                            checksum,
                            "en_US",
                            translations_hash,
                            dev=dev,
                            build=False,
                        )
                    )

    def test_the_dev_artifact_is_compiled_for_owl_dev_mode(self):
        production = self._precompiled().raw.decode()
        dev = self._precompiled(dev=True).raw.decode()
        self.assertTrue(production.rstrip().endswith("}, { dev: false });"))
        self.assertTrue(dev.rstrip().endswith("}, { dev: true });"))
        self.assertNotIn("Got duplicate key in t-foreach", production)
        self.assertIn("Got duplicate key in t-foreach", dev)

    def test_an_artifact_a_visitor_triggered_is_reused(self):
        visitor = self.env(user=self.env.ref("base.public_user"))
        first = self._precompiled(env=visitor)
        self.assertTrue(first)
        with patch(
            "odoo.addons.base.models.ir_qweb_assets_precompile.precompile_templates"
        ) as precompile:
            self.assertEqual(self._precompiled(env=visitor), first)
        precompile.assert_not_called()

    def test_the_artifact_is_per_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        english = self._precompiled("en_US").raw.decode()
        french = self._precompiled("fr_FR").raw.decode()
        self.assertIn('title="Close menu"', english)
        self.assertIn('title="Fermer le menu"', french)
        self.assertNotIn('title="Fermer le menu"', english)

    def test_an_artifact_is_refused_for_what_the_server_would_not_compile(self):
        IrQweb = self.env["ir.qweb"]
        checksum = self._pipeline().precompile_checksum()
        translations_hash = self._translations_hash("en_US")
        self.assertFalse(
            IrQweb._get_or_create_precompiled_template_attachment(
                BUNDLE, "0" * 16, "en_US", translations_hash
            ),
            "templates other than the bundle's",
        )
        self.assertFalse(
            IrQweb._get_or_create_precompiled_template_attachment(
                BUNDLE, checksum, "en_US", "f" * 64
            ),
            "translations other than the language's",
        )
        self.assertFalse(
            IrQweb._get_or_create_precompiled_template_attachment(
                BUNDLE, checksum, "xx_XX", translations_hash
            ),
            "a language that is not installed",
        )

    def test_a_host_without_the_precompiler_assembles_no_bundle_for_it(self):
        qweb = self.env["ir.qweb"]
        with (
            patch(
                "odoo.addons.base.models.ir_qweb_assets_precompile"
                ".precompiler_available",
                return_value=False,
            ),
            patch.object(type(qweb), "_precompile_templates") as build,
        ):
            self.assertFalse(qweb._precompiled_templates_available())
            self.assertFalse(self._precompiled())
        build.assert_not_called()

    def test_what_the_precompiler_lacks_is_named_once_with_its_fix(self):
        precompiler_missing.cache_clear()
        self.addCleanup(precompiler_missing.cache_clear)
        with (
            patch(
                "odoo.tools.assets.owl_precompile._NODE_PACKAGES",
                ("acorn", "a_package_nobody_installed"),
            ),
            self.assertLogs("odoo.assets.owl_precompile", "WARNING") as logs,
        ):
            self.assertIn(
                "node_modules/a_package_nobody_installed", precompiler_missing()
            )
            precompiler_missing()
        self.assertEqual(len(logs.output), 1)
        self.assertIn("npm ci", logs.output[0])

    def test_a_template_that_does_not_compile_is_left_to_the_browser(self):
        templates = {
            "pc.good": '<div t-name="pc.good">ok</div>',
            "pc.bad": '<div t-name="pc.bad"><t t-foreach="[1]" t-as="i"/></div>',
            "pc.custom": '<div t-name="pc.custom" t-custom-unknown="x"/>',
        }
        registrations = "\n".join(
            f'registerTemplate("{name}", "/pc/static/{name}.xml", `{xml}`);'
            for name, xml in templates.items()
        )
        with self.assertLogs("odoo.assets.owl_precompile", "INFO") as logs:
            result = precompile_templates(
                registrations, {}, web_static=web_static_path(), label="pc"
            )
        self.assertEqual(result.compiled, 1)
        self.assertEqual(set(result.failures), {"pc.bad", "pc.custom"})
        self.assertIn('"pc.good": [', result.script)
        self.assertNotIn('"pc.bad"', result.script)
        self.assertTrue(
            any("pc.bad left to the browser" in line for line in logs.output)
        )


@tagged("web_unit", "web_assets")
class TestPrecompiledTemplatesCleanup(PrecompiledTemplatesMixin, TransactionCase):
    def setUp(self):
        super().setUp()
        self.enterContext(
            patch.dict(
                "odoo.addons.base.models.ir_qweb_assets_precompile._recent_scripts",
                clear=True,
            )
        )
        self.translations_hash = self._translations_hash("en_US")

    def _store(self, checksum):
        IrQweb = self.env["ir.qweb"]
        url = IrQweb._get_precompiled_templates_url(
            BUNDLE, checksum, "en_US", self.translations_hash
        )
        return IrQweb._store_precompiled_templates(
            url, BUNDLE, "en_US", self.translations_hash, f"/* {checksum} */"
        )

    def _age(self, attachment, days):
        self.env.cr.execute(
            "UPDATE ir_attachment SET create_date = now() - make_interval(days => %s)"
            " WHERE id = %s",
            (days, attachment.id),
        )
        attachment.invalidate_recordset(["create_date"])

    def test_another_checksum_inside_the_grace_survives(self):
        first = self._store("a" * 16)
        second = self._store("b" * 16)
        self.assertTrue(first.exists(), "a variant still served was deleted")
        self.assertTrue(second.exists())

    def test_an_old_artifact_goes_once_the_grace_is_over(self):
        grace = self.env["ir.attachment"]._get_esm_gc_grace_days()
        oldest = self._store("a" * 16)
        previous = self._store("b" * 16)
        self._age(oldest, grace + 2)
        self._age(previous, grace + 1)
        current = self._store("c" * 16)
        self.assertFalse(oldest.exists())
        self.assertTrue(
            previous.exists(), "the version just replaced is still named by tabs"
        )
        self.assertTrue(current.exists())

    def test_a_twin_of_the_same_artifact_goes_at_once(self):
        first = self._store("a" * 16)
        second = self._store("a" * 16)
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())


@tagged("post_install", "-at_install", "web_assets")
class TestPrecompiledTemplatesInTheBrowser(PrecompiledTemplatesMixin, HttpCase):
    COMPARE_JS = """
        (async () => {
            const { templates } = odoo.loader.modules.get("@web/core/templates");
            const { loadJS } = odoo.loader.modules.get("@web/core/assets");
            const { TemplateSet } = odoo.loader.modules.get("@odoo/owl");
            const { makeAppConfig, getRootAppContext } =
                odoo.loader.modules.get("@web/env");
            const { code, translationsHash } =
                getRootAppContext().services.localization;
            if (code !== "__LANG__") {
                throw new Error(`the page runs in ${code}, not __LANG__`);
            }
            const checksum = templates.bundles.get("web.assets_web")?.checksum;
            if (!checksum) {
                throw new Error("web.assets_web announced no precompiled templates");
            }
            await loadJS(
                `/web/assets/owl/${checksum}/${code}/${translationsHash}/web.assets_web.js`,
            );
            const body = (fn) => {
                const source = fn.toString();
                return source.slice(source.indexOf("{") + 1, source.lastIndexOf("}"));
            };
            const compiler = new TemplateSet(makeAppConfig(undefined, { dev: false }));
            const names = Object.keys(templates.compiled.prod.named);
            const stale = [];
            const differ = [];
            for (const name of names) {
                const { fn } = templates.compiled.prod.named[name];
                if (templates.getCompiledTemplate(name) !== fn) {
                    stale.push(name);
                    continue;
                }
                const compiled = compiler._compileTemplate(name, templates.getTemplate(name));
                if (body(compiled) !== body(fn)) {
                    differ.push(name);
                }
            }
            if (names.length < 100 || stale.length || differ.length) {
                throw new Error(
                    `${names.length} precompiled, stale: ${stale.slice(0, 10)}, ` +
                    `differ: ${differ.slice(0, 10)}`,
                );
            }
            console.log(`${names.length} precompiled templates match`);
            console.log("test successful");
        })();
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        require_precompiler()

    PUBLIC_PAGE_JS = """
        (async () => {
            const { templates, inlineTemplateKey } =
                odoo.loader.modules.get("@web/core/templates");
            const { globalTemplates } = odoo.loader.modules.get("@odoo/owl");
            await templates.compiledTemplatesLoaded();
            const inline = Object.values(globalTemplates).filter(
                (template) => typeof template === "string",
            );
            const missing = [];
            for (const variant of ["prod", "dev"]) {
                const compiled = templates.compiled[variant];
                for (const source of inline) {
                    if (!compiled.inline[inlineTemplateKey(source)]) {
                        missing.push(`${variant}: ${source.slice(0, 80)}`);
                    }
                }
                for (const name of Object.keys(templates.templates)) {
                    if (!(name in compiled.named)) {
                        missing.push(`${variant}: ${name}`);
                    }
                }
            }
            if (inline.length < 10 || missing.length) {
                throw new Error(
                    `${inline.length} inline templates, not precompiled: ${missing.slice(0, 10)}`,
                );
            }
            console.log("test successful");
        })();
    """

    def test_a_public_page_has_every_template_compiled_by_the_server(self):
        self.browser_js(
            "/web/login",
            self.PUBLIC_PAGE_JS,
            ready="document.body.getAttribute('is-ready') === 'true'",
            timeout=180,
        )

    def test_the_route_serves_an_immutable_artifact(self):
        url = self.env["ir.qweb"]._get_precompiled_templates_url(
            BUNDLE,
            self._pipeline().precompile_checksum(),
            "en_US",
            self._translations_hash("en_US"),
        )
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("immutable", response.headers["Cache-Control"])
        self.assertIn(".registerCompiledTemplates({", response.text)
        missing = url.replace(self._pipeline().precompile_checksum(), "0" * 16)
        self.assertEqual(self.url_open(missing).status_code, 404)
        dev = self.url_open(url.removesuffix(".js") + ".dev.js")
        self.assertEqual(dev.status_code, 200)
        self.assertIn("{ dev: true });", dev.text)

    def test_a_cold_artifact_waiter_reads_committed_before_the_lock(self):
        from odoo.db.cursor import BaseCursor, Cursor

        url = self.env["ir.qweb"]._get_precompiled_templates_url(
            BUNDLE,
            self._pipeline().precompile_checksum(),
            "en_US",
            self._translations_hash("en_US"),
        )
        IrQweb = type(self.env["ir.qweb"])
        original = IrQweb._get_or_create_precompiled_template_attachment

        def cold_then_built(qweb, *args, build=True, **kwargs):
            if not build:
                return qweb.env["ir.attachment"]
            return original(qweb, *args, build=build, **kwargs)

        order = []
        original_execute = Cursor.execute
        original_rc = BaseCursor.use_read_committed

        def spy_execute(cr_self, query, params=None, **kwargs):
            if "pg_advisory_xact_lock" in str(query):
                order.append("lock")
            return original_execute(cr_self, query, params, **kwargs)

        def spy_rc(cr_self):
            order.append("read_committed")
            return original_rc(cr_self)

        with (
            patch.object(
                IrQweb,
                "_get_or_create_precompiled_template_attachment",
                cold_then_built,
            ),
            patch.object(Cursor, "execute", spy_execute),
            patch.object(BaseCursor, "use_read_committed", spy_rc),
        ):
            response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order[:2], ["read_committed", "lock"])

    def test_every_precompiled_template_is_what_the_browser_compiles(self):
        self._compare_in_the_browser("en_US")

    def test_a_translated_page_gets_the_code_its_browser_compiles(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.env.ref("base.user_admin").lang = "fr_FR"
        self._compare_in_the_browser("fr_FR")

    def _compare_in_the_browser(self, lang):
        code = self.COMPARE_JS.replace("__LANG__", lang)
        ready = "!!odoo.loader.modules.get('@web/env')?.getRootAppContext()"
        self.browser_js("/odoo", code, ready=ready, login="admin", timeout=180)


@tagged("post_install", "-at_install", "web_http", "web_assets")
class TestTemplatesPreload(HttpCase):
    URL = f"/web/assets/owl/0123456789abcdef/en_US/{'a' * 64}/{BUNDLE}.js"

    def _preloads(self, html):
        return [
            link
            for link in re.findall(r"<link\b[^>]*>", html)
            if 'rel="preload"' in link
        ]

    def test_the_preload_carries_the_nonce_the_script_policy_admits(self):
        self.authenticate("admin", "admin")
        with patch.object(
            self.registry["ir.qweb"],
            "_get_page_templates_url",
            lambda *_args, **_kwargs: self.URL,
        ):
            response = self.url_open("/odoo")
        response.raise_for_status()
        [link] = self._preloads(response.text)
        self.assertIn('as="script"', link)
        self.assertIn(f'href="{self.URL}"', link)
        nonce = re.search(r'nonce="([^"]+)"', link)
        self.assertTrue(nonce, "without the nonce the browser refuses the preload")
        self.assertIn(
            f"'nonce-{nonce[1]}'", response.headers["Content-Security-Policy"]
        )

    def test_a_page_with_no_artifact_to_ask_for_preloads_none(self):
        self.authenticate("admin", "admin")
        response = self.url_open("/odoo")
        response.raise_for_status()
        self.assertEqual(self._preloads(response.text), [])
