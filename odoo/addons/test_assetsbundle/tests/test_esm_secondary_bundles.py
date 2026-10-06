from types import SimpleNamespace
from unittest.mock import patch

from odoo.libs.json import loads as json_loads
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger
from odoo.tools.assets import esm_bridges, esm_graph
from odoo.tools.assets.esm_graph import discover_transitive_import_specifiers
from odoo.tools.assets.esm_registry import esm_registry

from .common import asset_file
from odoo.addons.base.models.assetsbundle import AssetsBundle
from odoo.addons.base.models.ir_qweb_assets_esbuild import (
    _get_specs_imported_by_consumers,
)


class TestBundleProductsAreMemoized(TransactionCase):
    TEMPLATE = '<templates><t t-name="test.audit.tpl"><div/></t></templates>'

    def test_generate_xml_bundle_renders_once(self):
        bundle = AssetsBundle(
            "test.audit.xml",
            [asset_file("/m/t.xml", self.TEMPLATE)],
            env=self.env,
        )
        first = bundle.generate_esm_template_bundle()
        with patch.object(
            type(bundle._xml), "_render_xml_bundle", side_effect=AssertionError
        ):
            self.assertEqual(bundle.generate_esm_template_bundle(), first)
        self.assertIn("test.audit.tpl", first)

    def test_bundles_with_the_same_template_files_share_one_render(self):
        template = '<templates><t t-name="test.shared.tpl"><i/></t></templates>'
        first = AssetsBundle(
            "test.shared.page", [asset_file("/m/shared.xml", template)], env=self.env
        )
        rendered = first._xml.generate_xml_bundle()
        again = AssetsBundle(
            "test.shared.child", [asset_file("/m/shared.xml", template)], env=self.env
        )
        with patch.object(
            type(again._xml), "_render_xml_bundle", side_effect=AssertionError
        ):
            self.assertEqual(again._xml.generate_xml_bundle(), rendered)
        changed = AssetsBundle(
            "test.shared.page",
            [asset_file("/m/shared.xml", template.replace("<i/>", "<b/>"))],
            env=self.env,
        )
        self.assertIn("<b/>", changed._xml.generate_xml_bundle())

    def test_a_failed_render_is_not_shared(self):
        broken = '<templates><t t-name="test.broken.tpl" t-inherit="x" t-inherit-mode="bogus"/></templates>'

        def render():
            return AssetsBundle(
                "test.broken", [asset_file("/m/broken.xml", broken)], env=self.env
            )._xml

        with mute_logger("odoo.addons.base.models.assetsbundle.assets"):
            self.assertIn("throw new Error", render().generate_xml_bundle())
            pipeline = render()
            with patch.object(
                type(pipeline),
                "_render_xml_bundle",
                wraps=pipeline._render_xml_bundle,
            ) as rendered:
                pipeline.generate_xml_bundle()
        rendered.assert_called_once()

    def test_native_module_data_is_computed_once_per_flag(self):
        bundle = AssetsBundle(
            "test.audit.esm",
            [asset_file("/m/a.js", "/** @odoo-module native */\nexport const a = 1;")],
            env=self.env,
        )
        first = bundle.get_native_module_data(with_bridges=False)
        with patch.object(
            type(bundle), "_native_module_data", side_effect=AssertionError
        ):
            self.assertIs(bundle.get_native_module_data(with_bridges=False), first)

    def test_the_two_bridge_variants_do_not_share_a_cache_entry(self):
        bundle = AssetsBundle(
            "test.audit.esm",
            [asset_file("/m/a.js", "/** @odoo-module native */\nexport const a = 1;")],
            env=self.env,
        )
        without = bundle.get_native_module_data(with_bridges=False)
        with patch.object(type(bundle), "_native_module_data", return_value="SENTINEL"):
            self.assertEqual(
                bundle.get_native_module_data(with_bridges=True), "SENTINEL"
            )
        self.assertEqual(without["bridge_import_map"], {})


class TestSecondaryBundlePageScope(TransactionCase):
    BUNDLE = "web.assets_tests"

    def _fake_bundles(self, inventory):
        def _get(_self, name, **kwargs):
            return SimpleNamespace(
                get_native_module_data=lambda **kw: {
                    "import_map": dict.fromkeys(inventory.get(name, ()), "/x.js")
                }
            )

        return patch.object(type(self.env["ir.qweb"]), "_get_asset_bundle", _get)

    def test_a_page_unions_its_bundles_while_a_declaration_intersects_them(self):
        IrQweb = self.env["ir.qweb"]
        inventory = {
            "a.backend": ("@shared/one", "@backend/only"),
            "b.frontend": ("@shared/one", "@frontend/only"),
        }
        with (
            self._fake_bundles(inventory),
            patch(
                "odoo.addons.base.models.ir_qweb_assets.esm_registry",
                return_value=SimpleNamespace(
                    secondary_parents={self.BUNDLE: ("a.backend", "b.frontend")},
                ),
            ),
            patch(
                "odoo.addons.base.models.ir_qweb_assets_import_map.esm_registry",
                return_value=SimpleNamespace(
                    secondary_parents={self.BUNDLE: ("a.backend", "b.frontend")},
                ),
            ),
        ):
            page = IrQweb._get_secondary_provider_specs(
                self.BUNDLE, None, ("a.backend", "b.frontend")
            )
            declared = IrQweb._get_secondary_provider_specs(self.BUNDLE, None, ())
        self.assertEqual(page, {"@shared/one", "@backend/only", "@frontend/only"})
        self.assertEqual(declared, {"@shared/one"})

    def test_the_page_scope_is_empty_for_a_bundle_that_is_not_secondary(self):
        IrQweb = self.env["ir.qweb"]
        self.assertEqual(IrQweb._get_esm_page_scope("web.assets_web"), ())

    def test_a_backend_only_module_is_externalised_on_a_backend_page(self):
        IrQweb = self.env["ir.qweb"]
        params = self.env["ir.asset"]._prepare_assets_params()
        backend = IrQweb._get_asset_bundle(
            "web.assets_web",
            js=True,
            css=False,
            debug_assets=False,
            assets_params=params,
        )
        backend_specs = set(
            backend.get_native_module_data(with_bridges=False)["import_map"]
        )
        secondary = IrQweb._get_asset_bundle(
            self.BUNDLE,
            js=True,
            css=False,
            debug_assets=False,
            assets_params=params,
        )
        own = set(secondary.get_native_module_data(with_bridges=False)["import_map"])
        if not own or not backend_specs:
            self.skipTest("bundles resolved empty (web assets unavailable)")
        discovered, _ext = secondary._bridges._discover_bridge_specifiers(
            own, set(IrQweb._external_libs())
        )
        backend_only = (set(discovered) & backend_specs) - own
        scoped = IrQweb._get_secondary_shared_specs(
            self.BUNDLE, params, ("web.assets_web",)
        )
        self.assertEqual(
            backend_only - set(scoped),
            set(),
            "a module the backend page already carries was left to esbuild, "
            "which inlines a second instance of it",
        )

    def test_a_provider_rendering_after_the_tests_bundle_is_reported(self):
        IrQweb = self.env["ir.qweb"]
        params = self.env["ir.asset"]._prepare_assets_params()
        declared = IrQweb._get_secondary_provider_specs(self.BUNDLE, params, ())
        if not declared:
            self.skipTest("no declared parents resolved (web assets unavailable)")
        with self.assertLogs("odoo.assets.esm", level="WARNING") as logs:
            IrQweb._get_secondary_shared_specs(
                self.BUNDLE, params, ("web.assets_frontend_minimal",)
            )
        self.assertTrue(
            any("secondary_provider_renders_late" in line for line in logs.output),
            logs.output,
        )


class TestEsmRegistryInstallationScope(TransactionCase):
    def _declarations(self):
        from odoo.modules import Manifest

        for manifest in Manifest.get_all_addon_manifests():
            esm = manifest.get("esm")
            if esm:
                yield manifest.name, esm

    def _claims_a_live_foreign_namespace(self, module, bundle):
        from odoo.modules import Manifest

        namespace = bundle.partition(".")[0]
        if namespace == module:
            return False
        return Manifest.for_addon(namespace, display_warning=False) is not None

    def test_a_module_only_registers_bundles_it_owns(self):
        stolen = [
            (module, bundle)
            for module, esm in self._declarations()
            for bundle in esm.get("bundles", ())
            if self._claims_a_live_foreign_namespace(module, bundle)
        ]

        self.assertFalse(stolen, f"modules registering foreign bundles: {stolen}")

    def _dependency_closure(self, module):
        from odoo.modules import Manifest

        closure, queue = set(), [module]
        while queue:
            manifest = Manifest.for_addon(queue.pop(), display_warning=False)
            for dep in (manifest and manifest["depends"]) or ():
                if dep not in closure:
                    closure.add(dep)
                    queue.append(dep)
        return closure

    def _wires_a_dependency_onto_its_own_page(self, module, parent, child):
        return parent.partition(".")[0] == module and child.partition(".")[
            0
        ] in self._dependency_closure(module)

    def test_child_declarations_stay_in_their_namespace(self):
        misplaced = [
            (module, key, child)
            for module, esm in self._declarations()
            for key in (
                "dynamic_children",
                "import_map_includes",
                "secondary_import_map_includes",
            )
            for parent, children in (esm.get(key) or {}).items()
            for child in children
            if self._claims_a_live_foreign_namespace(module, child)
            and not self._wires_a_dependency_onto_its_own_page(module, parent, child)
        ]

        self.assertFalse(
            misplaced, f"modules contributing foreign children: {misplaced}"
        )

    def test_absent_modules_contribute_empty_children_not_wrong_ones(self):
        registry = esm_registry()
        installed = self.env["ir.asset"]._get_addons_installed()
        absent = {
            child
            for children in registry.dynamic_children.values()
            for child in children
            if child.partition(".")[0] not in installed
        }
        if not absent:
            self.skipTest("every module declaring a dynamic child is installed")

        children = self.env["ir.qweb"]._get_dynamic_child_bundles(
            "web.assets_web",
            self.env["ir.asset"]._prepare_assets_params(),
            debug_assets=True,
        )
        built = {child.name: child for child in children}

        self.assertTrue(
            absent & set(built),
            "no absent child was built -- the registry became installation-aware",
        )
        for name in sorted(absent & set(built)):
            child = built[name]
            self.assertFalse(
                child.native_modules or child.javascripts,
                f"{name} is not installed yet contributed files to the import map",
            )


class TestSatelliteReachIsProvidedToRuntimeChildren(TransactionCase):
    PARENT = "web.assets_frontend"
    SATELLITE = "web.assets_tests"

    def test_what_the_satellite_registers_is_what_the_group_stubs(self):
        q = self.env["ir.qweb"]
        params = q.env["ir.asset"]._prepare_assets_params()
        if self.SATELLITE not in esm_registry().secondary_import_map_includes.get(
            self.PARENT, ()
        ):
            self.skipTest("the satellite is not declared under the parent")
        inlined = q._get_secondary_inlined_reach(
            self.SATELLITE, params, page_scope=(self.PARENT,)
        )
        if not inlined:
            self.skipTest("the satellite reaches nothing the page lacks")
        page = set(
            q._get_asset_bundle(
                self.PARENT,
                js=True,
                css=False,
                debug_assets=False,
                assets_params=params,
            ).get_native_module_data(with_bridges=False)["import_map"]
        )
        self.assertTrue(set(inlined).isdisjoint(page), "the page already carries it")
        without = q._get_runtime_parent_specs((self.PARENT,), params, False)
        with_satellites = q._get_runtime_parent_specs((self.PARENT,), params, True)
        self.assertTrue(set(inlined).isdisjoint(without))
        self.assertLessEqual(set(inlined), with_satellites)
        for spec, url in inlined.items():
            self.assertTrue(url.startswith("/") and url.endswith(".js"), (spec, url))


class TestAConsumersImportsAreReadOneWay(TransactionCase):
    SOURCE = (
        'export { a } from "@m/a";\nimport "@m/b";\n'
        'import { animationFrame } from "@odoo/hoot-mock";\nexport const c = 1;\n'
    )

    def _imported(self, members, source=SOURCE):
        consumer = AssetsBundle("test.audit.consumer", [], env=self.env)
        consumer.native_modules = [
            SimpleNamespace(
                module_path="@c/own",
                url="/c/static/src/own.js",
                raw_content=source,
            )
        ]
        return _get_specs_imported_by_consumers([consumer], members)

    def test_the_lexer_and_the_regex_name_the_same_members(self):
        members = {"@m/a", "@m/b", "@m/unused"}
        lexed = self._imported(members)
        with (
            patch.object(esm_bridges, "lex_module", return_value=None),
            patch.object(esm_graph, "lex_module", return_value=None),
        ):
            scanned = self._imported(members)
        self.assertEqual(lexed, {"@m/a", "@m/b"})
        self.assertEqual(scanned, lexed)

    def test_a_member_under_an_external_lib_name_is_imported(self):
        if "@odoo/hoot-mock" not in esm_registry().external_libs:
            self.skipTest("@odoo/hoot-mock is not an external lib here")
        # the bundle that owns it must export it, or a per-file test module
        # importing animationFrame from it reads undefined
        self.assertIn("@odoo/hoot-mock", self._imported({"@odoo/hoot-mock"}))

    def test_a_member_reexported_under_an_external_lib_name_is_imported(self):
        if "@odoo/hoot-mock" not in esm_registry().external_libs:
            self.skipTest("@odoo/hoot-mock is not an external lib here")
        reexport = 'export { animationFrame } from "@odoo/hoot-mock";\n'
        self.assertEqual(
            self._imported({"@odoo/hoot-mock"}, reexport), {"@odoo/hoot-mock"}
        )


class TestSatelliteReachIsRegisteredWhenServedPerFile(TransactionCase):
    PARENT = "web.assets_frontend"
    SATELLITE = "web.assets_tests"
    REACH = {"@web/views/view": "/web/static/src/views/view.js"}

    def test_the_per_file_satellite_maps_and_registers_its_reach(self):
        q = self.env["ir.qweb"]
        self.env.registry.clear_cache("assets")
        with patch.object(
            type(q), "_get_secondary_inlined_reach", lambda *_a, **_k: self.REACH
        ):
            pre, post = q._get_native_module_nodes_uncached(
                self.SATELLITE, page_scope=(self.PARENT,), esbuild_ok=False
            )
        [import_map] = [
            json_loads(node[1]["text"])["imports"]
            for node in pre
            if node[1].get("type") == "importmap"
        ]
        self.assertEqual(
            import_map.get("@web/views/view"), "/web/static/src/views/view.js"
        )
        bridge = "".join(node[1]["text"] for node in post if "data-bridge" in node[1])
        self.assertIn('"@web/views/view"', bridge)

    def test_a_debug_render_walks_the_satellite_reach_once_per_assets_cache(self):
        q = self.env["ir.qweb"]
        self.env.registry.clear_cache("assets")
        walks = []

        def reach(*_args, **_kwargs):
            walks.append(1)
            return self.REACH

        with patch.object(type(q), "_get_secondary_inlined_reach", reach):
            for _ in range(2):
                q._get_native_module_nodes_uncached(
                    self.SATELLITE, debug="assets", page_scope=(self.PARENT,)
                )
            self.env.registry.clear_cache("assets")
            q._get_native_module_nodes_uncached(
                self.SATELLITE, debug="assets", page_scope=(self.PARENT,)
            )
        self.assertEqual(len(walks), 2)


class TestSecondarySingletonSurface(TransactionCase):
    BUNDLE = "web.assets_tests"
    PARENT = "web.assets_web"

    def _specs(self, bundle):
        return set(
            self.env["ir.qweb"]
            ._get_asset_bundle(bundle, js=True, css=False, assets_params={})
            .get_native_module_data(with_bridges=False)["import_map"]
        )

    def test_every_stubbed_specifier_is_owned_by_the_parent(self):
        shared = self.env["ir.qweb"]._get_secondary_shared_specs(self.BUNDLE, {})
        if not shared:
            self.skipTest("no shared specifiers on this database")

        self.assertLessEqual(set(shared), self._specs(self.PARENT))

    def test_the_guarantee_covers_transitive_imports(self):
        IrQweb = self.env["ir.qweb"]
        scope = ("web.assets_frontend_lazy",)
        shared = set(IrQweb._get_secondary_shared_specs(self.BUNDLE, {}, scope))
        if not shared:
            self.skipTest("no shared specifiers on this database")
        provider_specs = self._specs(scope[0])
        own_specs = self._specs(self.BUNDLE)
        secondary = IrQweb._get_asset_bundle(
            self.BUNDLE, js=True, css=False, assets_params={}
        )
        direct, _ext = secondary._bridges._discover_bridge_specifiers(
            own_specs, set(IrQweb._external_libs())
        )
        inlined = set(direct) - provider_specs
        if not inlined:
            self.skipTest("every direct import is provided by the page")
        reachable = discover_transitive_import_specifiers(
            inlined,
            known_specifiers=own_specs | shared,
            ext_libs=IrQweb._external_libs(),
            bundle_name=self.BUNDLE,
        )
        self.assertEqual(
            reachable & provider_specs,
            set(),
            "a module the page already carries is reachable through an inlined "
            "import, so esbuild inlines a second instance of it",
        )
