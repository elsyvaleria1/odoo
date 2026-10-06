import re
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase
from odoo.tools.assets import esm_graph, esm_index
from odoo.tools.assets.esm_graph import url_to_module_path
from odoo.tools.misc import file_path

INLINED = "test_assetsbundle.esm_inlined"
HELPER = "test_assetsbundle/static/tests/esm_inlined/unlisted/helper.js"
_INPUT_RE = re.compile(
    r"(?:^|/)(?P<addon>[\w.-]+)/static/(?P<kind>src|lib|tests)/(?P<rest>.+)$"
)
# a module reached by a bare specifier resolves through the addon resolution
# root, `<data_dir>/esbuild-roots/<digest>/@addon` -> `addon/static/src`
_ROOT_INPUT_RE = re.compile(
    r"/esbuild-roots/[0-9a-f]+/@(?P<addon>[\w.-]+)/(?P<rest>.+)$"
)


class TestTheSourceKeyCoversWhatEsbuildReads(TransactionCase):
    def _compile(self, bundle, **kwargs):
        qweb = self.env["ir.qweb"]
        params = self.env["ir.asset"]._prepare_assets_params()
        asset_bundle = qweb._get_asset_bundle(
            bundle, js=True, css=False, assets_params=params
        )
        keyed = {}
        source_key = esm_index.source_key

        def spy(*args, **kw):
            keyed.update(args=args, kwargs=kw)
            return source_key(*args, **kw)

        with patch.object(esm_index, "source_key", spy):
            result, _children = qweb._compile_with_esbuild_locked(
                bundle, asset_bundle, params, **kwargs
            )
        self.assertTrue(result.metafile, f"{bundle} was not compiled")
        return json_loads(result.metafile)["inputs"], keyed

    def _unkeyed_inputs(self, bundle, **kwargs):
        inputs, keyed = self._compile(bundle, **kwargs)
        args, kw = keyed["args"], keyed["kwargs"]
        keyed_specs = {
            *(module.module_path for module in args[1]),
            *args[3],
            *(kw.get("registered_reach") or ()),
            *kw["inlined_sources"],
        }
        unkeyed = []
        for path in inputs:
            if path == "<stdin>":
                continue
            if root_match := _ROOT_INPUT_RE.search(path):
                url = f"/{root_match['addon']}/static/src/{root_match['rest']}"
            else:
                match = _INPUT_RE.search(path)
                self.assertIsNotNone(match, f"{path} is read but names no module")
                url = f"/{match['addon']}/static/{match['kind']}/{match['rest']}"
            if url_to_module_path(url) not in keyed_specs:
                unkeyed.append(path)
        return unkeyed

    def test_an_unlisted_import_and_a_literal_import_call_are_keyed(self):
        self.assertEqual(self._unkeyed_inputs(INLINED, standalone=True), [])

    def test_every_input_of_a_page_bundle_is_keyed(self):
        self.assertEqual(self._unkeyed_inputs("web.assets_frontend_lazy"), [])

    def test_editing_an_unlisted_helper_changes_the_key(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        copy = tmp / "helper.js"
        shutil.copy(file_path(HELPER), copy)
        real_file_path = esm_graph.file_path

        def redirected(rel, *args, **kwargs):
            if rel == HELPER:
                return str(copy)
            return real_file_path(rel, *args, **kwargs)

        qweb = self.env["ir.qweb"]
        asset_bundle = qweb._get_asset_bundle(
            INLINED, js=True, css=False, assets_params={}
        )
        with patch.object(esm_graph, "file_path", redirected):
            before = qweb._esm_source_key(INLINED, asset_bundle, None, {}, None)
            copy.write_text('export const helperValue = "edited";\n', encoding="utf-8")
            after = qweb._esm_source_key(INLINED, asset_bundle, None, {}, None)
        self.assertNotEqual(before, after)

    def _inlined(self, source, reached=(), provided=()):
        module = SimpleNamespace(
            module_path="@test_assetsbundle/own",
            url="/test_assetsbundle/static/src/own.js",
            raw_content=source,
        )
        return self.env["ir.qweb"]._inlined_module_sources(
            INLINED, [module], reached, provided
        )

    def test_a_registered_reach_is_keyed_by_its_text(self):
        inlined = self._inlined(
            "export const own = 1;\n", reached=("@web/core/registry",)
        )
        self.assertIn("@web/core/registry", inlined)
        self.assertIn("export const registry", inlined["@web/core/registry"])

    def test_a_specifier_a_stub_provides_is_not_keyed(self):
        source = 'import { registry } from "@web/core/registry";\n'
        self.assertIn("@web/core/registry", self._inlined(source))
        self.assertNotIn(
            "@web/core/registry",
            self._inlined(source, provided={"@web/core/registry"}),
        )
