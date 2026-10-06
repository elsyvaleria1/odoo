import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import lxml.html
from lxml import etree
from markupsafe import Markup

from odoo.http.core import _request_stack
from odoo.libs.json import loads as json_loads
from odoo.modules.module import get_module_path
from odoo.tests.common import HttpCase, TransactionCase, tagged

NONCE_RE = re.compile(r"'nonce-([A-Za-z0-9_-]+)'")
HANDLER_RE = re.compile(r"^on[a-z]+$")


class CspPageAssertions:
    def assertPageScriptsNonced(self, url, login=None):
        if login:
            self.authenticate(login, login)
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200, url)
        policy = response.headers.get("Content-Security-Policy", "")
        match = NONCE_RE.search(policy)
        self.assertTrue(match, f"{url} carries no nonce policy: {policy!r}")
        self.assertIn("'strict-dynamic'", policy)
        nonce = match.group(1)
        document = lxml.html.document_fromstring(response.content)
        scripts = list(document.iter("script"))
        self.assertTrue(scripts, f"{url} renders no script")
        for element in [*scripts, *document.xpath("//link[@rel='modulepreload']")]:
            self.assertEqual(
                element.get("nonce"),
                nonce,
                f"{url}: {lxml.html.tostring(element)[:200]!r}",
            )
        for element in document.iter(etree.Element):
            handlers = [name for name in element.attrib if HANDLER_RE.match(name)]
            self.assertFalse(handlers, f"{url}: inline handler on <{element.tag}>")
            href = (element.get("href") or "").strip().lower()
            self.assertFalse(href.startswith("javascript:"), f"{url}: {href}")
        return nonce


@tagged("web_unit", "web_qweb")
class TestScriptNonceInjection(TransactionCase):
    def _request(self, nonce):
        return patch.object(
            type(self.env["ir.qweb"]), "_script_nonce", return_value=nonce
        )

    def _render(self, arch, values=None):
        return self.env["ir.qweb"]._render(
            etree.fromstring(arch), values or {}, minimal_qcontext=True
        )

    def test_a_static_script_carries_the_request_nonce(self):
        arch = '<div><p>x</p><script type="module">let a = 1;</script></div>'
        with self._request("n0nce"):
            html = self._render(arch)
        self.assertEqual(
            html,
            '<div><p>x</p><script type="module" nonce="n0nce">let a = 1;</script></div>',
        )

    def test_the_compiled_template_does_not_freeze_the_nonce(self):
        arch = "<div><script>1</script></div>"
        with self._request("first"):
            first = self._render(arch)
        with self._request("second"):
            second = self._render(arch)
        self.assertIn('nonce="first"', first)
        self.assertIn('nonce="second"', second)

    def test_a_dynamic_script_carries_the_request_nonce(self):
        arch = """<div>
            <script t-att-src="src"/>
            <script t-if="True" type="module">2</script>
        </div>"""
        with self._request("n0nce"):
            html = self._render(arch, {"src": "/a.js"})
        self.assertIn('<script src="/a.js" nonce="n0nce"></script>', html)
        self.assertIn('<script type="module" nonce="n0nce">2</script>', html)

    def test_a_literal_nonce_is_replaced_and_a_computed_one_kept(self):
        arch = """<div>
            <script nonce="served-last-week">1</script>
            <script nonce="" t-if="True">2</script>
            <script t-att-nonce="mine">3</script>
        </div>"""
        with self._request("n0nce"):
            html = self._render(arch, {"mine": "computed"})
        self.assertEqual(html.count("nonce="), 3)
        self.assertIn('<script nonce="n0nce">1</script>', html)
        self.assertIn('<script nonce="n0nce">2</script>', html)
        self.assertIn('<script nonce="computed">3</script>', html)

    def test_a_script_that_reaches_the_page_as_a_value_carries_no_nonce(self):
        arch = """<div>
            <t t-out="injected"/>
            <p t-att-title="attribute"/>
            <t t-out="text"/>
        </div>"""
        with self._request("n0nce"):
            html = self._render(
                arch,
                {
                    "injected": Markup("<script>steal()</script>"),
                    "attribute": '"><script>steal()</script>',
                    "text": "<script>steal()</script>",
                },
            )
        self.assertNotIn("n0nce", html)
        self.assertEqual(html.count("<script>steal()</script>"), 1)

    def test_the_nonce_is_the_bound_request_s(self):
        qweb = self.env["ir.qweb"]
        for bound, expected in (("n0nce", "n0nce"), (object(), None)):
            _request_stack.push(SimpleNamespace(csp_nonce=bound))
            try:
                self.assertEqual(qweb._script_nonce(), expected)
            finally:
                _request_stack.pop()
        self.assertIsNone(qweb._script_nonce())

    def test_without_a_request_no_nonce_is_written(self):
        html = self._render(
            "<div><script>1</script><script t-att-src='s'/></div>", {"s": "/x"}
        )
        self.assertNotIn("nonce", html)

    def test_asset_script_tags_carry_the_request_nonce(self):
        arch = (
            '<div><t t-call-assets="web.assets_frontend_minimal" t-css="false"/></div>'
        )
        with self._request("n0nce"):
            html = self._render(arch)
        document = lxml.html.fragment_fromstring(html)
        scripts = list(document.iter("script"))
        self.assertTrue(scripts)
        for script in scripts:
            self.assertEqual(script.get("nonce"), "n0nce", lxml.html.tostring(script))

    def test_trusted_html_field_scripts_carry_the_request_nonce(self):
        converter = self.env["ir.qweb.field.html"]
        value = Markup('<p>x</p><script src="/y.js"></script>')
        with self._request("n0nce"):
            trusted = converter.value_to_html(value, {"trusted_scripts": True})
            untrusted = converter.value_to_html(value, {})
        self.assertIn('<script src="/y.js" nonce="n0nce"></script>', trusted)
        self.assertNotIn("nonce", untrusted)

    def test_only_unsanitized_html_fields_are_trusted(self):
        partner = self.env["res.partner"].create({"name": "p"})
        options = self.env["ir.qweb.field.html"]._record_options(partner, "comment", {})
        self.assertNotIn("trusted_scripts", options)


@tagged("post_install", "-at_install")
class TestServedPagesScriptPolicy(CspPageAssertions, HttpCase):
    def test_login_page(self):
        first = self.assertPageScriptsNonced("/web/login")
        second = self.assertPageScriptsNonced("/web/login")
        self.assertNotEqual(first, second)

    def test_backend_web_client(self):
        self.assertPageScriptsNonced("/odoo", login="admin")

    def test_html_report(self):
        module = self.env.ref("base.module_base")
        self.assertPageScriptsNonced(
            f"/report/html/web.report_irmodulereference/{module.id}", login="admin"
        )

    def test_offline_page(self):
        self.assertPageScriptsNonced("/odoo/offline")


@tagged("post_install", "-at_install")
class TestPublicPagesRunWithoutEval(HttpCase):
    def _policy(self, url):
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200, url)
        return response.headers["Content-Security-Policy"]

    def test_the_login_page_runs_without_unsafe_eval(self):
        policy = self._policy("/web/login")
        self.assertNotIn("'unsafe-eval'", policy)
        self.assertIn("'strict-dynamic'", policy)

    def test_the_backend_client_keeps_unsafe_eval(self):
        self.authenticate("admin", "admin")
        self.assertIn("'unsafe-eval'", self._policy("/odoo"))

    def test_debug_assets_keep_unsafe_eval(self):
        self.assertIn("'unsafe-eval'", self._policy("/web/login?debug=assets"))

    def test_without_the_precompiler_a_public_page_keeps_unsafe_eval(self):
        with patch(
            "odoo.addons.base.models.ir_qweb_assets_precompile.precompiler_available",
            return_value=False,
        ):
            self.assertIn("'unsafe-eval'", self._policy("/web/login"))

    def test_a_page_that_also_loads_another_bundle_keeps_unsafe_eval(self):
        qweb = self.env["ir.qweb"]
        self.assertFalse(
            qweb._is_script_bundle_eval_needed("web.assets_frontend_lazy", "")
        )
        self.assertTrue(qweb._is_script_bundle_eval_needed("web.assets_web", ""))
        self.assertTrue(qweb._is_script_bundle_eval_needed("web.assets_backend", ""))


class TestOwlCompilerFollowsEval(HttpCase):
    # @odoo/owl is owl's runtime build; a page imports the compiler module
    # exactly when one of its bundles may compile a template in the browser,
    # which is when it keeps 'unsafe-eval'
    def _page(self, url):
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200, url)
        document = lxml.html.document_fromstring(response.content)
        return response.headers["Content-Security-Policy"], list(
            document.iter("script")
        )

    def _import_map(self, scripts):
        imports = {}
        for script in scripts:
            if script.get("type") == "importmap":
                imports.update(json_loads(script.text)["imports"])
        return imports

    def _compiler_scripts(self, scripts):
        return [script for script in scripts if script.get("data-owl-compiler")]

    def assertCompilerBeforeItsBundle(self, scripts):
        compilers = self._compiler_scripts(scripts)
        self.assertTrue(compilers)
        for compiler in compilers:
            self.assertEqual(compiler.get("type"), "module")
            self.assertEqual(compiler.text.strip(), 'import "@odoo/owl/compiler";')
            at = scripts.index(compiler)
            self.assertTrue(
                any(script.get("type") == "importmap" for script in scripts[:at]),
                "the compiler import comes before any import map",
            )
            bundle = compiler.get("data-owl-compiler")
            self.assertTrue(
                any(
                    script.get("data-bridge") == bundle
                    or bundle in (script.get("src") or "")
                    for script in scripts[at + 1 :]
                ),
                f"{bundle}: no script of the bundle after its compiler import",
            )

    def test_the_backend_client_imports_the_compiler(self):
        self.authenticate("admin", "admin")
        policy, scripts = self._page("/odoo")
        self.assertIn("'unsafe-eval'", policy)
        self.assertCompilerBeforeItsBundle(scripts)

    def test_an_eval_free_page_loads_the_runtime_alone(self):
        policy, scripts = self._page("/web/login")
        self.assertNotIn("'unsafe-eval'", policy)
        self.assertEqual(self._compiler_scripts(scripts), [])
        imports = self._import_map(scripts)
        self.assertIn("owl.runtime", imports["@odoo/owl"])
        self.assertIn("owl.compiler", imports["@odoo/owl/compiler"])

    def test_debug_assets_import_the_compiler(self):
        policy, scripts = self._page("/web/login?debug=assets")
        self.assertIn("'unsafe-eval'", policy)
        self.assertCompilerBeforeItsBundle(scripts)

    def test_without_the_precompiler_a_public_page_imports_the_compiler(self):
        with patch(
            "odoo.addons.base.models.ir_qweb_assets_precompile.precompiler_available",
            return_value=False,
        ):
            policy, scripts = self._page("/web/login")
        self.assertIn("'unsafe-eval'", policy)
        self.assertCompilerBeforeItsBundle(scripts)

    def test_a_loaded_bundle_says_whether_it_may_compile(self):
        qweb = self.env["ir.qweb"]
        self.assertFalse(qweb._is_loaded_bundle_eval_needed("web.assets_emoji", ""))
        self.assertTrue(qweb._is_loaded_bundle_eval_needed("web.assets_clickbot", ""))
        self.assertTrue(
            qweb._is_loaded_bundle_eval_needed("web.assets_emoji", "assets")
        )
        self.authenticate("admin", "admin")
        for bundle, expected in (
            ("web.assets_emoji", False),
            ("web.assets_clickbot", True),
        ):
            response = self.url_open(f"/web/bundle/{bundle}")
            self.assertEqual(response.status_code, 200, bundle)
            self.assertIs(response.json()["owl_compiler"], expected, bundle)


@tagged("post_install", "-at_install")
class TestNoInlineEventHandlerInTemplates(TransactionCase):
    def test_no_installed_template_carries_an_inline_handler(self):
        offenders = []
        views = (
            self.env["ir.ui.view"]
            .with_context(active_test=False)
            .search([("type", "=", "qweb")])
        )
        for view in views:
            if not view.arch_db:
                continue
            root = etree.fromstring(view.arch_db.encode())
            for element in root.iter(etree.Element):
                if element.tag == "t":
                    continue
                for name, value in element.attrib.items():
                    if HANDLER_RE.match(name) or (
                        name in ("href", "t-attf-href")
                        and value.strip().lower().startswith("javascript:")
                    ):
                        offenders.append(
                            f"{view.xml_id or view.id}: <{element.tag} {name}>"
                        )
        self.assertEqual(offenders, [])

    def test_no_client_template_carries_an_inline_handler(self):
        offenders = []
        modules = self.env["ir.module.module"].search([("state", "=", "installed")])
        for module in modules:
            path = get_module_path(module.name, display_warning=False)
            if not path:
                continue
            for xml_path in sorted(Path(path, "static", "src").glob("**/*.xml")):
                root = etree.parse(xml_path).getroot()
                for element in root.iter(etree.Element):
                    tag = etree.QName(element).localname
                    if tag == "t" or not tag[0].islower():
                        continue
                    offenders.extend(
                        f"{xml_path}: <{tag} {name}>"
                        for name in element.attrib
                        if HANDLER_RE.match(name)
                    )
        self.assertEqual(offenders, [])


@tagged("post_install", "-at_install")
class TestBrowserReportsRefusedScripts(HttpCase):
    def test_a_script_without_the_nonce_fails_the_browser_run(self):
        code = """
            const script = document.createElement("script");
            script.textContent = "window.cspProbe = 1";
            document.head.append(script);
            const button = document.createElement("button");
            button.setAttribute("onclick", "window.cspProbe = 2");
            document.body.append(button);
            button.click();
            setTimeout(() => console.log(window.cspProbe ? "ran" : "test successful"), 500);
        """
        with (
            self.assertLogs(level="ERROR"),
            self.assertRaises(AssertionError) as caught,
            patch("odoo.tests.common.ChromeBrowser.take_screenshot", return_value=None),
        ):
            self.browser_js("/web/login", code, timeout=30)
        self.assertIn("CSP violation", caught.exception.args[0])
