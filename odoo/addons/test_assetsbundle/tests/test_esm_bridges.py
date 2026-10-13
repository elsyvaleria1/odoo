import shutil
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote

from odoo.tests.common import TransactionCase
from odoo.tools.assets.esm_bridges import BridgeShimManager
from odoo.tools.assets.esm_graph import _bridge_shim_source
from odoo.tools.assets.esm_registry import external_lib_aliases
from odoo.tools.json import scriptsafe as json
from odoo.tools.misc import file_path

from .common import _Mod, set_cursor_readonly_until_cleanup
from odoo.addons.base.models.assetsbundle import AssetsBundle


class TestFallbackBridgeExternals(TransactionCase):
    def test_an_unrelated_bundle_bridges_owl_and_nothing_else(self):
        IrQweb = self.env["ir.qweb"]
        specs = IrQweb._bridge_external_specifiers(
            {"import_map": {"@web/env": "/web/static/src/env.js"}}
        )
        self.assertEqual(specs, {"@odoo/owl"})

    def test_a_bundle_carrying_hoot_bridges_its_aliases(self):
        IrQweb = self.env["ir.qweb"]
        aliases = external_lib_aliases()
        hoot = {spec: aliases[spec] for spec in ("@odoo/hoot", "@odoo/hoot-dom")}
        self.assertEqual(
            hoot,
            {
                "@odoo/hoot": "@web/../lib/hoot/hoot",
                "@odoo/hoot-dom": "@web/../lib/hoot-dom/hoot-dom",
            },
            "the alias of a declared library is its own URL read as a specifier",
        )
        specs = IrQweb._bridge_external_specifiers(
            {"import_map": dict.fromkeys(hoot.values(), "/web/static/lib/x.js")}
        )
        self.assertEqual(specs, {"@odoo/owl", *hoot})

    def test_the_app_bundles_do_not_bridge_the_test_framework(self):
        IrQweb = self.env["ir.qweb"]
        params = self.env["ir.asset"]._prepare_assets_params()
        for bundle in ("web.assets_web", "web.assets_frontend_lazy"):
            asset_bundle = IrQweb._get_asset_bundle(
                bundle,
                js=True,
                css=False,
                debug_assets=True,
                assets_params=params,
            )
            native_data = asset_bundle.get_native_module_data()
            if not native_data["import_map"]:
                self.skipTest(f"{bundle} resolved empty (web assets unavailable)")
            self.assertEqual(
                IrQweb._bridge_external_specifiers(native_data),
                {"@odoo/owl"},
                f"{bundle} would evaluate the HOOT test framework on every page "
                "served through the per-file fallback",
            )


class BridgeRequestBoundCase(TransactionCase):
    def setUp(self):
        super().setUp()
        self.enterContext(patch("odoo.http.request", new=SimpleNamespace()))


class TestBridgeShimLiterals(TransactionCase):
    NAMES = {"alpha", "class", "default", "a-b"}

    def test_shim_specifier_is_json_quoted(self):
        shim, is_fallback = _bridge_shim_source("@web/core/x", {"alpha"}, True)
        self.assertIn('odoo.loader.modules.get("@web/core/x");', shim)
        self.assertNotIn("get('@web/core/x')", shim)
        self.assertIn("_e0 = _m.alpha;", shim)
        self.assertIn("_e0 as alpha", shim)
        self.assertNotIn("export default", shim)
        self.assertFalse(is_fallback)

    def test_a_reserved_word_survives_as_an_alias(self):
        shim, _ = _bridge_shim_source("@web/core/x", self.NAMES, False)

        self.assertIn(" as class", shim)
        self.assertNotIn("const class", shim)
        self.assertNotIn("a-b", shim)
        self.assertNotIn("= _m.default;", shim)

    @unittest.skipUnless(shutil.which("node"), "node binary not available")
    def test_the_two_generators_agree(self):
        bridge_js = file_path("web/static/src/core/module_bridge.js")
        names = sorted(self.NAMES)
        script = (
            f"import {{ getBridgeModuleSource }} from {json.dumps(bridge_js)};\n"
            f"process.stdout.write("
            f"getBridgeModuleSource({json.dumps('@web/core/x')}, "
            f"{json.dumps(names)}));\n"
        )

        proc = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        python_shim, _ = _bridge_shim_source("@web/core/x", self.NAMES, False)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, python_shim)


class TestBridgeHashWidth(BridgeRequestBoundCase):
    def test_bridge_url_hash_is_32_hex(self):
        bundle = AssetsBundle("web.assets_web", [], env=self.env)
        with patch.object(
            BridgeShimManager,
            "_create_bridge_attachments_via_rw_cursor",
            return_value=None
        ):
            urls = bundle._bridges._get_or_create_bridge_urls(
                {"@web/test_hash": "export default 1;"}
            )
        basename = urls["@web/test_hash"].rsplit("/", 1)[-1]
        self.assertRegex(basename, r"^[0-9a-f]{32}\.js$")


class TestBridgeReadonlyEscalation(BridgeRequestBoundCase):
    def _set_cursor_readonly_until_cleanup(self):
        set_cursor_readonly_until_cleanup(self)

    def test_escalation_success_returns_canonical_urls(self):
        bundle = AssetsBundle("web.assets_web", [], env=self.env)
        self._set_cursor_readonly_until_cleanup()
        with patch.object(
            BridgeShimManager,
            "_create_bridge_attachments_via_rw_cursor",
            return_value=None
        ) as escalate:
            urls = bundle._bridges._get_or_create_bridge_urls(
                {"@web/ro_test": "export default 1;"}
            )
        escalate.assert_called_once()
        (to_create,) = escalate.call_args.args
        self.assertEqual(len(to_create), 1)
        self.assertTrue(urls["@web/ro_test"].startswith("/web/assets/esm/bridges/"))

    def test_escalation_failure_falls_back_to_data_uris(self):
        bundle = AssetsBundle("web.assets_web", [], env=self.env)
        self._set_cursor_readonly_until_cleanup()
        with patch.object(
            BridgeShimManager,
            "_create_bridge_attachments_via_rw_cursor",
            side_effect=RuntimeError("primary unavailable")
        ) as escalate:
            urls = bundle._bridges._get_or_create_bridge_urls(
                {"@web/ro_test2": "export default 2;"}
            )
        escalate.assert_called_once()
        self.assertTrue(urls["@web/ro_test2"].startswith("data:text/javascript"))


class TestBridgePersistenceDecoupled(BridgeRequestBoundCase):
    def test_writable_cursor_routes_through_rw_cursor(self):
        bundle = AssetsBundle("web.assets_web", [], env=self.env)
        self.assertFalse(
            self.env.cr.readonly, "precondition: the request cursor is writable"
        )
        with patch.object(
            BridgeShimManager,
            "_create_bridge_attachments_via_rw_cursor",
            return_value=None
        ) as escalate:
            urls = bundle._bridges._get_or_create_bridge_urls(
                {"@web/decoupled": "export const decoupled = 1;"}
            )
        escalate.assert_called_once()
        url = urls["@web/decoupled"]
        self.assertTrue(
            url.startswith("/web/assets/esm/bridges/"),
            "a successful out-of-band persist yields a canonical URL",
        )
        self.assertFalse(
            url.startswith("data:"), "the writable path must not inline data: URIs"
        )

    def test_unwritable_primary_falls_back_to_data_uris(self):
        bundle = AssetsBundle("web.assets_web", [], env=self.env)
        with patch.object(
            BridgeShimManager,
            "_create_bridge_attachments_via_rw_cursor",
            side_effect=RuntimeError("primary unavailable")
        ):
            urls = bundle._bridges._get_or_create_bridge_urls(
                {"@web/degraded": "export const degraded = 2;"}
            )
        self.assertTrue(
            urls["@web/degraded"].startswith("data:text/javascript"),
            "data: URIs are reserved for a genuinely unwritable primary",
        )

    def test_failure_inlines_only_missing_bridge_content(self):
        manager = AssetsBundle("web.assets_web", [], env=self.env)._bridges
        with patch("odoo.http.request", None):
            reused = manager._get_or_create_bridge_urls(
                {"@probe/reused": "export const reused = 7;"}
            )["@probe/reused"]
        missing_source = "export const missing = 'café / ? # %';"
        with (
            patch.object(
                BridgeShimManager,
                "_create_bridge_attachments_via_rw_cursor",
                side_effect=RuntimeError("primary unavailable"),
            ) as create,
            self.assertLogs("odoo.tools.assets.esm_bridges", level="DEBUG") as logged,
        ):
            urls = manager._get_or_create_bridge_urls(
                {
                    "@probe/reused": "export const reused = 7;",
                    "@probe/missing": missing_source,
                    "@probe/same_content": missing_source,
                }
            )
        self.assertEqual(urls["@probe/reused"], reused)
        self.assertEqual(urls["@probe/missing"], urls["@probe/same_content"])
        self.assertEqual(unquote(urls["@probe/missing"].split(",", 1)[1]), missing_source)
        create.assert_called_once()
        self.assertEqual(len(create.call_args.args[0]), 1)
        self.assertIn("failed; falling back to data: URIs", "\n".join(logged.output))


class TestBridgeNoRequestPersistence(TransactionCase):
    def test_no_request_persists_on_current_cursor(self):
        bundle = AssetsBundle("web.assets_web", [], env=self.env)
        with patch.object(
            BridgeShimManager, "_create_bridge_attachments_via_rw_cursor"
        ) as escalate:
            urls = bundle._bridges._get_or_create_bridge_urls(
                {"@web/no_request": "export const no_request = 3;"}
            )
        escalate.assert_not_called()
        url = urls["@web/no_request"]
        self.assertTrue(
            url.startswith("/web/assets/esm/bridges/"),
            "current-cursor persistence still yields canonical URLs",
        )
        attachment = self.env["ir.attachment"].sudo().search([("url", "=", url)])
        self.assertTrue(
            attachment,
            "the bridge row must be visible on the current cursor",
        )

    def test_identical_sources_share_one_attachment_and_are_reused(self):
        manager = AssetsBundle("web.assets_web", [], env=self.env)._bridges
        sources = dict.fromkeys(
            ("@probe/first", "@probe/second"), "export const shared_probe = 11;"
        )
        urls = manager._get_or_create_bridge_urls(sources)
        self.assertEqual(urls["@probe/first"], urls["@probe/second"])
        attachments = self.env["ir.attachment"].sudo().search(
            [("url", "=", urls["@probe/first"])]
        )
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments.raw, sources["@probe/first"].encode())
        with patch.object(
            type(attachments), "create", side_effect=AssertionError("unexpected creation")
        ):
            self.assertEqual(manager._get_or_create_bridge_urls(sources), urls)


class TestBridgeShimSources(TransactionCase):
    def _manager(self):
        return AssetsBundle("web.assets_web", [], env=self.env)._bridges

    def test_a_shim_re_exports_the_real_module_names(self):
        shims = self._manager().prepare_shim_sources({"@web/core/registry"})
        shim = shims["@web/core/registry"]
        self.assertIn('odoo.loader.modules.get("@web/core/registry")', shim)
        self.assertRegex(
            shim,
            r"(_e\d+) = _m\.registry;",
            "the shim must bind each name to a local before re-exporting it",
        )
        self.assertRegex(shim, r"_e\d+ as registry\b")

    def test_no_specifiers_means_no_work(self):
        with patch(
            "odoo.tools.assets.esm_bridges._BridgeExportResolver",
            side_effect=AssertionError("unexpected source resolution"),
        ):
            self.assertEqual(self._manager().prepare_shim_sources(set()), {})

    def test_source_preparation_needs_no_database_environment(self):
        manager = self._manager()
        del manager.env
        for strict, wait in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(strict=strict, wait=wait):
                shim = manager.prepare_shim_sources(
                    {"@web/core/registry"}, strict=strict, wait=wait
                )["@web/core/registry"]
                self.assertRegex(shim, r"_e\d+ as registry\b")
                if strict:
                    self.assertIn("throw new Error(", shim)
                    self.assertNotIn("await new Promise(", shim)
                else:
                    self.assertEqual("await new Promise(" in shim, wait)

    def test_persisted_and_inline_bridges_have_the_same_source(self):
        manager = self._manager()
        specifiers = {"@web/core/registry", "@probe/missing_module"}
        sources = manager.prepare_shim_sources(specifiers)
        urls, fallback_count = manager._get_or_create_bridge_urls_and_fallback_count(
            specifiers
        )
        self.assertEqual(fallback_count, 1)
        for specifier, url in urls.items():
            attachment = self.env["ir.attachment"].sudo().search([("url", "=", url)])
            self.assertEqual(attachment.raw.decode(), sources[specifier])

    def test_a_strict_stub_throws_instead_of_waiting(self):
        stub = self._manager().prepare_shim_sources(
            {"@web/core/registry"}, strict=True
        )["@web/core/registry"]
        self.assertIn('odoo.loader.modules.get("@web/core/registry")', stub)
        self.assertIn("throw new Error(", stub)
        self.assertNotIn(
            "addEventListener",
            stub,
            "a runtime child evaluates after its parent registered, so the "
            "stub reads once and fails loudly instead of listening",
        )
        self.assertRegex(stub, r"const (_e\d+) = _m\.registry;")
        self.assertRegex(stub, r"_e\d+ as registry\b")
        self.assertIn("_d as default", stub)

    def test_discovery_reads_every_import_form(self):
        modules = [
            _Mod("@a/one", 'import def from "@web/core/a";\n'),
            _Mod("@a/two", 'import * as ns from "@web/core/b";\n'),
            _Mod("@a/three", 'import { named } from "@web/core/c";\n'),
        ]
        discovered, ext_seen = self._manager()._discover_bridge_specifiers(
            set(), set(), modules=modules
        )
        self.assertEqual(
            list(discovered), ["@web/core/a", "@web/core/b", "@web/core/c"]
        )
        self.assertEqual(ext_seen, set())

    def test_a_re_export_is_an_edge_esbuild_follows_so_it_is_bridged(self):
        modules = [
            _Mod("@a/facade", 'export { x } from "@web/core/a";\n'),
            _Mod("@a/star", 'export * from "@web/core/b";\n'),
            _Mod("@a/dflt", 'export { default } from "@web/core/c";\n'),
        ]
        discovered, _ext = self._manager()._discover_bridge_specifiers(
            set(), set(), modules=modules
        )
        self.assertEqual(
            list(discovered), ["@web/core/a", "@web/core/b", "@web/core/c"]
        )

    def test_the_reach_walks_through_a_facade_the_page_does_not_provide(self):
        modules = [
            _Mod("@a/one", 'import { actionService } from "@web/webclient/actions";\n')
        ]
        provided = {"@web/core/registry", "@web/core/browser/router"}
        direct, _ext = self._manager()._discover_bridge_specifiers(
            set(), set(), modules=modules
        )
        reached, _ext = self._manager()._discover_reachable_specifiers(
            set(), set(), provided=provided, modules=modules
        )
        self.assertEqual(set(direct), {"@web/webclient/actions"})
        self.assertIn("@web/webclient/actions/action_service", reached)
        self.assertLessEqual(provided, set(reached))

    def test_a_bundle_member_is_not_bridged_to_itself(self):
        modules = [_Mod("@a/one", 'import { x } from "@a/two";\n')]
        discovered, _ext = self._manager()._discover_bridge_specifiers(
            {"@a/two"}, set(), modules=modules
        )
        self.assertNotIn("@a/two", discovered)

    def test_an_external_library_is_recorded_but_not_bridged(self):
        modules = [_Mod("@a/one", 'import { App } from "@odoo/owl";\n')]
        discovered, ext_seen = self._manager()._discover_bridge_specifiers(
            set(), {"@odoo/owl"}, modules=modules
        )
        self.assertNotIn("@odoo/owl", discovered)
        self.assertEqual(ext_seen, {"@odoo/owl"})


class TestParentSelfBridge(TransactionCase):
    def _manager(self, *modules):
        bundle = AssetsBundle("web.assets_web", [], env=self.env)
        manager = bundle._bridges
        manager.native_modules = list(modules)
        return manager

    def test_every_owned_specifier_gets_a_shim(self):
        manager = self._manager(
            _Mod("@a/one", "export const ONE = 1;\n"),
            _Mod("@a/two", "export const TWO = 2;\n"),
        )
        with self.assertLogs("odoo.assets.bridge", level="DEBUG"):
            bridges = manager._get_or_create_parent_self_bridge_urls()

        self.assertEqual(sorted(bridges), ["@a/one", "@a/two"])
        self.assertTrue(
            all(
                url.startswith(("data:", "/web/assets/esm/bridges/"))
                for url in bridges.values()
            )
        )

    def test_a_star_reexport_is_resolved_from_the_bundle_not_from_disk(self):
        manager = self._manager(
            _Mod("@a/base", "export const A = 1;\nexport const B = 2;\n"),
            _Mod("@a/face", "export * from './base';\nexport const C = 3;\n"),
        )
        captured = {}
        with (
            patch.object(
                type(manager),
                "_get_or_create_bridge_urls",
                lambda _self, shims: captured.update(shims) or {},
            ),
            self.assertLogs("odoo.assets.bridge", level="DEBUG"),
        ):
            manager._get_or_create_parent_self_bridge_urls()

        shim = captured["@a/face"]
        for name in ("A", "B", "C"):
            self.assertRegex(shim, rf"_e\d+ as {name}\b", f"{name} missing")

    def test_a_relative_specifier_is_not_bridged(self):
        manager = self._manager(
            _Mod("@a/one", "export const ONE = 1;\n"),
            _Mod("../legacy/thing", "export const X = 1;\n"),
        )
        with self.assertLogs("odoo.assets.bridge", level="DEBUG"):
            bridges = manager._get_or_create_parent_self_bridge_urls()

        self.assertEqual(list(bridges), ["@a/one"])

    def test_no_native_modules_means_no_bridges(self):
        manager = self._manager()
        self.assertEqual(manager._get_or_create_parent_self_bridge_urls(), {})

    def test_parent_source_preparation_needs_no_database_environment(self):
        manager = self._manager(
            _Mod("@a/base", "export const BASE = 1;\n"),
            _Mod("@a/face", "export * from './base';\nexport const OWN = 2;\n"),
        )
        del manager.env
        sources = manager._prepare_parent_self_shim_sources().sources_by_specifier
        self.assertEqual(list(sources), ["@a/base", "@a/face"])
        for name in ("BASE", "OWN"):
            self.assertRegex(sources["@a/face"], rf"_e\d+ as {name}\b")


class TestBridgeRwCursorEscalation(TransactionCase):
    registry_test_mode = False
    URL_PREFIX = "/web/assets/esm/bridges/rwprobe"

    def setUp(self):
        super().setUp()
        self._cleanup_rows()

    def _cleanup_rows(self):
        from odoo.modules.registry import Registry
        from odoo.tests.common import get_db_name

        with Registry(get_db_name()).cursor() as cr:
            cr.execute(
                "DELETE FROM ir_attachment WHERE url LIKE %s", (self.URL_PREFIX + "%",)
            )
            cr.commit()

    def _to_create(self, name):
        return [
            {
                "name": name,
                "url": f"{self.URL_PREFIX}_{name}",
                "type": "binary",
                "public": True,
                "res_model": "ir.ui.view",
                "res_id": False,
                "raw": b"export default 1;",
                "mimetype": "text/javascript",
            }
        ]

    def test_the_rows_really_land_on_the_other_cursor(self):
        from odoo.modules.registry import Registry
        from odoo.tests.common import get_db_name

        self.addCleanup(self._cleanup_rows)
        manager = AssetsBundle("web.assets_web", [], env=self.env)._bridges

        self.assertIsNone(
            manager._create_bridge_attachments_via_rw_cursor(self._to_create("ok"))
        )

        with Registry(get_db_name()).cursor() as cr:
            cr.execute(
                "SELECT count(*) FROM ir_attachment WHERE url = %s",
                (f"{self.URL_PREFIX}_ok",),
            )
            self.assertEqual(cr.fetchone()[0], 1)

    def test_a_failed_creation_rolls_back_and_raises(self):
        manager = AssetsBundle("web.assets_web", [], env=self.env)._bridges
        bad = self._to_create("bad")
        bad[0]["no_such_field_on_ir_attachment"] = 1

        with self.assertRaises(ValueError):
            manager._create_bridge_attachments_via_rw_cursor(bad)
        self.assertFalse(
            self.env["ir.attachment"].sudo().search([("url", "=", bad[0]["url"])])
        )
