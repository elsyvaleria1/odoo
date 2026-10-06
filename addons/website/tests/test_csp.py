from unittest.mock import patch

import lxml.html

from odoo.tests.common import HttpCase, TransactionCase, tagged

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.web.tests.test_csp import CspPageAssertions
from odoo.addons.web.tests.test_precompiled_templates import require_precompiler


@tagged("post_install", "-at_install")
class TestWebsiteScriptPolicy(CspPageAssertions, HttpCase):
    def test_public_pages(self):
        for url in ("/", "/contactus", "/website/search?search=a"):
            self.assertPageScriptsNonced(url)

    def test_a_cached_page_runs_under_each_response_nonce(self):
        WebsitePage = type(self.env["website.page"])
        self.url_open("/")
        with patch.object(
            WebsitePage,
            "_get_response_raw",
            autospec=True,
            side_effect=WebsitePage._get_response_raw,
        ) as render:
            cached = self.assertPageScriptsNonced("/")
            cached_twice = self.assertPageScriptsNonced("/")
            with patch.object(WebsitePage, "_CACHE_DURATION", -1):
                rerendered = self.assertPageScriptsNonced("/")
            rerender_cached = self.assertPageScriptsNonced("/")
        self.assertEqual(render.call_count, 1)
        self.assertEqual(len({cached, cached_twice, rerendered, rerender_cached}), 4)

    def test_a_public_page_runs_without_unsafe_eval_cached_or_not(self):
        # a cache hit renders no t-call-assets: the policy rides on the cache
        WebsitePage = type(self.env["website.page"])
        rendered = [
            self.url_open(url).headers["Content-Security-Policy"]
            for url in ("/", "/contactus")
        ]
        with patch.object(
            WebsitePage,
            "_get_response_raw",
            autospec=True,
            side_effect=WebsitePage._get_response_raw,
        ) as render:
            cached = [
                self.url_open(url).headers["Content-Security-Policy"]
                for url in ("/", "/contactus")
            ]
        self.assertEqual(render.call_count, 0)
        for policy in rendered + cached:
            self.assertNotIn("'unsafe-eval'", policy)

    def test_a_page_an_editor_opens_keeps_unsafe_eval(self):
        # the builder loads its editor into the page it previews
        self.assertIn('"await_precompiled_templates": true', self.url_open("/").text)
        self.authenticate("admin", "admin")
        for url in ("/", "/contactus"):
            response = self.url_open(url)
            policy = response.headers["Content-Security-Policy"]
            self.assertIn("'unsafe-eval'", policy, url)
            # nor does it hold its boot for every artifact the server compiles
            self.assertIn('"await_precompiled_templates": false', response.text, url)

    def test_a_cached_page_hands_no_visitor_another_visitors_session(self):
        WebsitePage = type(self.env["website.page"])
        self.url_open("/")
        visitor = self.opener
        session_id = visitor.cookies["session_id"]
        self.opener = type(visitor)(self)
        with patch.object(WebsitePage, "_CACHE_DURATION", -1):
            self.url_open("/")
        self.assertNotEqual(self.opener.cookies["session_id"], session_id)
        self.opener = visitor
        self.url_open("/")
        self.assertEqual(visitor.cookies["session_id"], session_id)

    def test_editor_page(self):
        self.assertPageScriptsNonced("/", login="admin")

    def test_not_found_page(self):
        response = self.url_open("/csp-no-such-page")
        self.assertEqual(response.status_code, 404)
        self.assertIn("'strict-dynamic'", response.headers["Content-Security-Policy"])

    def test_custom_code_scripts_run_under_the_page_nonce(self):
        website = self.env["website"].get_current_website()
        website.custom_code_head = '<script id="csp_head">window.a = 1;</script>'
        website.custom_code_footer = '<script id="csp_foot" src="/x.js"></script>'
        nonce = self.assertPageScriptsNonced("/")
        document = lxml.html.document_fromstring(self.url_open("/").content)
        self.assertEqual(len(document.xpath("//script[@id='csp_head']")), 1)
        self.assertEqual(len(document.xpath("//script[@id='csp_foot']")), 1)
        self.assertTrue(nonce)

    def test_unsanitized_html_field_scripts_are_trusted(self):
        website = self.env["website"].get_current_website()
        options = self.env["ir.qweb.field.html"]._record_options(
            website, "custom_code_head", {}
        )
        self.assertTrue(options.get("trusted_scripts"))


@tagged("post_install", "-at_install")
class TestWebsitePrecompiledTemplates(TransactionCase):
    BUNDLE = "web.assets_frontend_lazy"

    def test_a_website_s_own_templates_are_rebuilt_with_its_params(self):
        # a public page on a website with assets of its own announces a
        # checksum only that website's bundle yields; the artifact route
        # rebuilt the bundle without it and 404ed, and the page, run without
        # 'unsafe-eval', could not compile in the browser either
        require_precompiler()
        website = self.env["website"].create({"name": "Own assets"})
        self.env["ir.asset"].create(
            {
                "name": "own template",
                "bundle": self.BUNDLE,
                "path": "website/static/src/components/fullscreen_indication/"
                "fullscreen_indication.xml",
                "website_id": website.id,
            }
        )
        IrQweb = self.env["ir.qweb"]
        params = {"website_id": website.id}
        pipeline = IrQweb._get_asset_bundle(
            self.BUNDLE, css=False, js=True, assets_params=params
        )._xml
        checksum = pipeline.precompile_checksum()
        self.assertNotEqual(
            checksum,
            IrQweb._get_asset_bundle(
                self.BUNDLE, css=False, js=True, assets_params={}
            )._xml.precompile_checksum(),
        )
        self.assertIn(
            f'registerTemplateBundle("{self.BUNDLE}", "{checksum}", '
            f'{{"website_id": {website.id}}}, () => {{\n',
            pipeline.generate_esm_template_bundle(use_import=False),
        )
        IrHttp = self.env["ir.http"]
        # what the artifact route runs in: a request that is not a website page
        with MockRequest(self.env, is_frontend=False):
            modules = IrHttp._get_webclient_translation_modules()[0]
            translations_hash = IrHttp._get_web_translations_hash(modules, "en_US")
            args = (self.BUNDLE, checksum, "en_US", translations_hash)
            self.assertFalse(IrQweb._get_or_create_precompiled_template_attachment(*args))
            artifact = IrQweb._get_or_create_precompiled_template_attachment(*args, assets_params=params)
        self.assertIn('"website.FullscreenIndication": [', artifact.raw.decode())

    def test_a_website_without_assets_of_its_own_ships_the_same_bundle(self):
        # the params in the announcement made every website's compiled bundle
        # other bytes: a new website compiled each bundle again, and a
        # read-only cursor, which cannot save them, served its modules one by one
        IrQweb = self.env["ir.qweb"]
        first = self.env["website"].search([], limit=1)
        second = self.env["website"].create({"name": "No assets of its own"})
        bundles = [
            IrQweb._get_asset_bundle(
                self.BUNDLE,
                css=False,
                js=True,
                assets_params={"website_id": website.id},
            )
            for website in (first, second)
        ]
        self.assertEqual([bundle.js_rebuild_params for bundle in bundles], [{}, {}])
        first_code, second_code = (
            bundle.generate_esm_template_bundle(use_import=False) for bundle in bundles
        )
        self.assertIn(f'registerTemplateBundle("{self.BUNDLE}", "', second_code)
        self.assertEqual(first_code, second_code)
