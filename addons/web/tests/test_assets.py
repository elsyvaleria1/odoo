import gzip
import hashlib
import logging
import time
from compression import zstd
from unittest.mock import patch

import odoo
import odoo.tests
from odoo.db.cursor import BaseCursor, Cursor
from odoo.libs.json import dumps as json_dumps
from odoo.modules.module import get_manifest
from odoo.tests.common import HttpCase, tagged
from odoo.tools import mute_logger
from odoo.tools.sass_embedded import SassCompileError, close_sass_compiler

from odoo.addons.base.models.assetsbundle.css_pipeline import CssPipeline
from odoo.addons.base.models.assetsbundle.js_pipeline import (
    ModuleSyntaxInLegacyBundleError,
)

_logger = logging.getLogger(__name__)


class TestAssetsGenerateTimeCommon(odoo.tests.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(close_sass_compiler)

    def generate_bundles(self, unlink=True):
        if unlink:
            self.env["ir.attachment"].search(
                [("url", "=like", "/web/assets/%")]
            ).unlink()
        installed_module_names = (
            self.env["ir.module.module"]
            .search([("state", "=", "installed")])
            .mapped("name")
        )
        bundles = {
            key
            for module in installed_module_names
            for key in get_manifest(module).get("assets", [])
            if not any(seg.startswith("_") for seg in key.split("."))
        }

        for bundle_name in bundles:
            with mute_logger(
                "odoo.addons.base.models.assetsbundle", "odoo.assets.bundle"
            ):
                for assets_type in "css", "js":
                    try:
                        start_t = time.time()
                        css = assets_type == "css"
                        js = assets_type == "js"
                        bundle = self.env["ir.qweb"]._get_asset_bundle(
                            bundle_name, css=css, js=js
                        )
                        if assets_type == "css" and bundle.stylesheets:
                            bundle.css()
                        if assets_type == "js" and bundle.javascripts:
                            bundle.js()
                        yield (
                            f"{bundle_name}.{assets_type}",
                            time.time() - start_t,
                        )
                    except (
                        ValueError,
                        SassCompileError,
                        ModuleSyntaxInLegacyBundleError,
                    ):
                        _logger.info(
                            "Error detected while generating bundle %r %s",
                            bundle_name,
                            assets_type,
                        )


@odoo.tests.tagged(
    "post_install", "-at_install", "assets_bundle", "web_unit", "web_assets"
)
class TestLogsAssetsGenerateTime(TestAssetsGenerateTimeCommon):
    def test_logs_assets_generate_time(self):
        for bundle, duration in list(self.generate_bundles()):
            _logger.info("Bundle %r generated in %.2fs", bundle, duration)

    def test_logs_assets_check_time(self):
        start = time.time()
        for bundle, duration in self.generate_bundles(False):
            _logger.info("Bundle %r checked in %.2fs", bundle, duration)
        duration = time.time() - start
        _logger.info("All bundle checked in %.2fs", duration)


@odoo.tests.tagged(
    "post_install",
    "-at_install",
    "-standard",
    "test_assets",
    "web_http",
    "web_assets",
)
class TestPregenerateTime(HttpCase):
    def test_logs_pregenerate_time(self):
        self.env["ir.qweb"]._pregenerate_assets_bundles()
        start = time.time()
        self.env.registry.clear_cache()
        self.env.cache.invalidate()
        with self.profile(
            collectors=[
                "sql",
                odoo.tools.profiler.PeriodicCollector(interval=0.01),
            ],
            disable_gc=True,
        ):
            self.env["ir.qweb"]._pregenerate_assets_bundles()
        duration = time.time() - start
        _logger.info("All bundle checked in %.2fs", duration)


@odoo.tests.tagged(
    "post_install",
    "-at_install",
    "-standard",
    "assets_bundle",
    "web_unit",
    "web_assets",
)
class TestAssetsGenerateTime(TestAssetsGenerateTimeCommon):
    def test_assets_generate_time(self):
        thresholds = {
            "project.webclient.js": 2.5,
            "point_of_sale.pos_assets_backend.js": 2.5,
            "web.assets_backend.js": 2.5,
        }
        for bundle, duration in self.generate_bundles():
            threshold = thresholds.get(bundle, 2)
            self.assertLess(
                duration,
                threshold,
                f"Bundle {bundle!r} took more than {threshold} sec",
            )


@odoo.tests.tagged("post_install", "-at_install", "web_http", "web_assets")
class TestLoad(HttpCase):
    def test_assets_already_exists(self):
        self.authenticate("admin", "admin")
        _save_attachment = (
            odoo.addons.base.models.assetsbundle.AssetsBundle.save_attachment
        )

        def save_attachment(bundle, extension, content):
            attachment = _save_attachment(bundle, extension, content)
            message = f"Trying to save an attachment for {bundle.name} when it should already exist: {attachment.url}"
            _logger.error(message)
            return attachment

        with patch(
            "odoo.addons.base.models.assetsbundle.AssetsBundle.save_attachment",
            save_attachment,
        ):
            self.url_open("/odoo").raise_for_status()
            self.url_open("/").raise_for_status()


@odoo.tests.tagged("post_install", "-at_install", "web_http", "web_assets")
class TestWebAssetsCursors(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bundle_name = "web.assets_frontend"
        cls.bundle_version = (
            cls.env["ir.qweb"]._get_asset_bundle(cls.bundle_name).get_version("css")
        )

    def setUp(self):
        super().setUp()
        self.env["ir.attachment"].search([("url", "=like", "/web/assets/%")]).unlink()
        self.bundle_name = "web.assets_frontend"

    def _get_generate_cursors_readwriteness(self):
        cursors = []
        original_cursor = self.env.registry.cursor

        def cursor(readonly=False, *, pin_key=None):
            cursor = original_cursor(readonly=readonly, pin_key=pin_key)
            cursors.append(
                (
                    "ro" if cursor.readonly else "rw",
                    "(ro_requested)" if readonly else "(rw_requested)",
                )
            )
            return cursor

        with patch.object(self.env.registry, "cursor", cursor):
            response = self.url_open(
                f"/web/assets/{self.bundle_version}/{self.bundle_name}.min.css",
                allow_redirects=False,
            )
            self.assertEqual(response.status_code, 200)

        return cursors

    def test_web_binary_keep_cursor_ro(self):
        self.assertEqual(
            self._get_generate_cursors_readwriteness(),
            [
                ("ro", "(ro_requested)"),
                ("rw", "(rw_requested)"),
            ],
            "A ro and rw cursor should be used to generate assets with replica when cold",
        )

        self.assertEqual(
            self._get_generate_cursors_readwriteness(),
            [
                ("ro", "(ro_requested)"),
            ],
            "Only one readonly cursor should be used to generate assets with replica when warm",
        )

    def test_web_binary_keep_cursor_rw(self):
        self.set_registry_readonly_mode(False)
        self.assertEqual(
            self._get_generate_cursors_readwriteness(),
            [
                ("rw", "(ro_requested)"),
                ("rw", "(rw_requested)"),
            ],
            "Generating takes a cursor of its own even without replica: the "
            "request's cursor cannot switch to READ COMMITTED before the lock",
        )


@odoo.tests.tagged("post_install", "-at_install", "web_http", "web_assets")
class TestAssetEncodings(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        bundle = cls.env["ir.qweb"]._get_asset_bundle("web.assets_frontend")
        cls.url = f"/web/assets/{bundle.get_version('css')}/web.assets_frontend.min.css"

    def setUp(self):
        super().setUp()
        self.env["ir.attachment"].search([("url", "=like", "/web/assets/%")]).unlink()

    def _get(self, accept_encoding):
        response = self.opener.get(
            self.base_url() + self.url,
            headers={"Accept-Encoding": accept_encoding},
            stream=True,
            timeout=60,
        )
        response.raise_for_status()
        return response, response.raw.read(decode_content=False)

    def test_a_bundle_is_served_in_the_encoding_the_client_accepts(self):
        # the first request builds the bundle, the second reads it back
        for attempt in ("built", "stored"):
            with self.subTest(attempt=attempt):
                response, body = self._get("gzip, deflate, br, zstd")
                self.assertEqual(response.headers["Content-Encoding"], "zstd")
                self.assertIn("Accept-Encoding", response.headers["Vary"])
                self.assertEqual(
                    response.headers["Content-Type"], "text/css; charset=utf-8"
                )
                plain, raw = self._get("identity")
                self.assertNotIn("Content-Encoding", plain.headers)
                self.assertIn("Accept-Encoding", plain.headers["Vary"])
                self.assertEqual(zstd.decompress(body), raw)
                self.assertLess(len(body), len(raw) // 3)

        response, body = self._get("gzip")
        self.assertEqual(response.headers["Content-Encoding"], "gzip")
        self.assertEqual(gzip.decompress(body), raw)


@tagged("post_install", "-at_install")
class TestWebAssetsRegenerationLock(HttpCase):
    def test_a_stylesheet_error_banner_is_not_cached(self):
        bundle_name = "web.assets_frontend"
        self.env["ir.attachment"].search(
            [("url", "=like", f"/web/assets/%/{bundle_name}.min.css")]
        ).unlink()
        version = self.env["ir.qweb"]._get_asset_bundle(bundle_name).get_version("css")
        url = f"/web/assets/{version}/{bundle_name}.min.css"

        def failing_compile(pipeline, compiler, source):
            pipeline._bundle.css_errors.append("Sass: timed out")
            return ""

        with (
            patch.object(CssPipeline, "compile_css", failing_compile),
            mute_logger("odoo.addons.base.models.assetsbundle"),
        ):
            banner = self.url_open(url, allow_redirects=False)
        self.assertEqual(banner.status_code, 200)
        self.assertIn(CssPipeline._CSS_ERROR_HEADER.strip(), banner.text)
        self.assertNotIn("immutable", banner.headers.get("Cache-Control", ""))

        recovered = self.url_open(url, allow_redirects=False)
        self.assertNotIn(CssPipeline._CSS_ERROR_HEADER.strip(), recovered.text)
        self.assertIn("immutable", recovered.headers.get("Cache-Control", ""))

    def test_an_unhashed_asset_url_is_not_immutable(self):
        response = self.url_open(
            "/web/assets/any/web.assets_frontend.min.css", allow_redirects=False
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("immutable", response.headers.get("Cache-Control", ""))

    def test_the_waiter_reads_committed_before_it_takes_the_lock(self):
        # a waiter must see the stylesheet the lock holder committed: its
        # transaction is READ COMMITTED before the lock statement starts it
        bundle_name = "web.assets_frontend"
        self.env["ir.attachment"].search(
            [("url", "=like", f"/web/assets/%/{bundle_name}.min.css")]
        ).unlink()
        version = self.env["ir.qweb"]._get_asset_bundle(bundle_name).get_version("css")
        url = f"/web/assets/{version}/{bundle_name}.min.css"
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
            patch.object(Cursor, "execute", spy_execute),
            patch.object(BaseCursor, "use_read_committed", spy_rc),
        ):
            response = self.url_open(url, allow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(order[:2], ["read_committed", "lock"])

    def test_regeneration_takes_a_stable_per_bundle_advisory_lock(self):
        bundle_name = "web.assets_frontend"
        self.env["ir.attachment"].search(
            [("url", "=like", f"/web/assets/%/{bundle_name}.min.css")]
        ).unlink()
        version = self.env["ir.qweb"]._get_asset_bundle(bundle_name).get_version("css")
        url = f"/web/assets/{version}/{bundle_name}.min.css"

        lock_calls = []
        original_execute = Cursor.execute

        def spy_execute(cr_self, query, params=None, **kwargs):
            if "pg_advisory_xact_lock" in str(query):
                lock_calls.append(params)
            return original_execute(cr_self, query, params, **kwargs)

        with patch.object(Cursor, "execute", spy_execute):
            response = self.url_open(url, allow_redirects=False)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            len(lock_calls), 1, "Expected exactly one advisory lock acquisition"
        )
        digest = hashlib.blake2b(
            f"{bundle_name}.min.css".encode(), digest_size=8
        ).digest()
        expected_key = int.from_bytes(digest, "big", signed=True)
        self.assertEqual(lock_calls[0], (expected_key,))


@tagged("post_install", "-at_install")
class TestTemporalPolyfill(HttpCase):
    def _run_shim(self, delete_temporal):
        # the page's own loader shim, run while a fresh document still parses,
        # with each script carrying the page's CSP nonce as the shim's does
        self.browser_js(
            "/web/login",
            f"""
            const shimNode = document.querySelector("script[data-loader-shim]");
            const nonce = shimNode.nonce;
            const frame = document.createElement("iframe");
            document.body.append(frame);
            const doc = frame.contentWindow.document;
            const tag = (code) => `<script nonce="${{nonce}}">${{code}}<\\/script>`;
            doc.open();
            doc.write(
                tag({"'delete window.Temporal; delete window.odoo;'" if delete_temporal else "'delete window.odoo;'"}) +
                tag(shimNode.textContent) +
                tag("window.__seen = typeof Temporal === 'function' || typeof Temporal === 'object' ? Temporal.PlainDate.from('2024-02-29').add({{ years: 1 }}).toString() : 'missing';")
            );
            doc.close();
            const started = Date.now();
            (function wait() {{
                const seen = frame.contentWindow.__seen;
                if (seen === undefined && Date.now() - started < 10000) {{
                    return setTimeout(wait, 50);
                }}
                const polyfill = doc.querySelector('script[src$="/temporal-polyfill/temporal-polyfill.js"]');
                const result = JSON.stringify({{
                    seen,
                    written: Boolean(polyfill),
                    nonce: polyfill ? polyfill.nonce === nonce : null,
                }});
                const expected = JSON.stringify({json_dumps({"seen": "2025-02-28", "written": delete_temporal, "nonce": True if delete_temporal else None})});
                if (result === expected) {{
                    console.log("test successful");
                }} else {{
                    console.error("got " + result + ", expected " + expected);
                }}
            }})();
            """,
            "Boolean(document.querySelector('script[data-loader-shim]'))",
        )

    def test_a_browser_without_temporal_gets_the_polyfill_before_the_next_script(self):
        self._run_shim(delete_temporal=True)

    def test_a_browser_with_temporal_loads_nothing(self):
        self._run_shim(delete_temporal=False)

    def test_the_polyfill_is_served(self):
        response = self.url_open(
            "/web/static/lib/temporal-polyfill/temporal-polyfill.js"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("temporal-polyfill 1.0.5", response.text)


@tagged("post_install", "-at_install")
class TestBrowserFloorNotice(HttpCase):
    def test_every_esm_page_carries_the_check_and_the_notice(self):
        html = self.url_open("/web/login").text
        self.assertIn('id="web.layout.browser_check"', html)
        self.assertIn('id="o_browser_unsupported"', html)

    def _rerun_check(self, setup_js, expect_notice):
        # rerun the page's own check under a simulated browser
        self.browser_js(
            "/web/login",
            f"""
            {setup_js}
            const code = document.getElementById("web.layout.browser_check").textContent;
            new Function(code)();
            window.dispatchEvent(new Event("__after_check"));
            const shown = Boolean(document.querySelector("body > .o_browser_unsupported"));
            if (shown === {"true" if expect_notice else "false"}) {{
                console.log("test successful");
            }} else {{
                console.error("notice shown: " + shown);
            }}
            """,
            # parsed, not only started: the check defers its notice to
            # DOMContentLoaded while the document is still loading
            "document.readyState !== 'loading'",
        )

    def test_a_browser_reporting_no_import_maps_gets_the_notice(self):
        self._rerun_check("HTMLScriptElement.supports = () => false;", True)

    def test_a_browser_without_supports_and_no_error_keeps_the_page(self):
        # Chrome/Edge 89-95: import maps work, supports() does not exist yet
        self._rerun_check("delete HTMLScriptElement.supports;", False)

    def test_a_browser_without_supports_whose_bundle_fails_gets_the_notice(self):
        # what Chrome 79 produced: a SyntaxError in a compiled bundle
        self._rerun_check(
            """
            delete HTMLScriptElement.supports;
            window.addEventListener("__after_check", () =>
                window.dispatchEvent(new ErrorEvent("error", {
                    message: "Uncaught SyntaxError: Unexpected token '.'",
                    filename: location.origin + "/web/assets/1/web.assets_frontend_minimal.esm.js",
                }))
            );
            """,
            True,
        )

    def test_a_supported_browser_keeps_the_page(self):
        self.browser_js(
            "/web/login",
            """
            if (document.querySelector("body > .o_browser_unsupported")) {
                console.error("a supported browser got the notice");
            } else {
                console.log("test successful");
            }
            """,
            "Boolean(document.querySelector('.oe_login_form'))",
        )
