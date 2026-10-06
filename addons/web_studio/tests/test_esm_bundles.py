from odoo.tests.common import TransactionCase, tagged
from odoo.tools.assets.esm_registry import esm_registry


@tagged("-at_install", "post_install")
class TestStudioEsmBundles(TransactionCase):
    def test_studio_bundles_are_dynamic_esm(self):
        dynamic = esm_registry().dynamic_bundle_names
        for name in ("web_studio.studio_assets", "web_studio.studio_assets_dark"):
            self.assertIn(
                name,
                dynamic,
                f"{name} must be a dynamic ESM child so /web/bundle serves it as ESM",
            )

    def test_studio_dark_bundle_assembles(self):
        nodes = self.env["ir.qweb"]._get_asset_nodes(
            "web_studio.studio_assets_dark", css=True, js=False
        )
        self.assertTrue(nodes, "dark studio bundle must produce CSS nodes")
