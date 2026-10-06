from unittest.mock import patch

from odoo.tests.common import HttpCase, tagged
from odoo.tools.assets.esm_registry import esm_registry


@tagged("-at_install", "post_install", "web_assets")
class TestPageAssetsWarm(HttpCase):
    """What the master computes before it forks must be what a page reads: an
    entry under another key is warmed for nobody."""

    def _warmed_bundles(self):
        registry = esm_registry()
        return (
            set(registry.classic_page_bundles)
            | set(registry.page_secondaries)
            | {
                parent
                for bundle in registry.page_secondaries
                for parent in registry.secondary_parents[bundle]
            }
        )

    def test_the_first_pages_of_a_warmed_worker_compute_no_asset_of_their_bundles(self):
        IrQweb = self.env["ir.qweb"]
        self.env.registry.clear_cache("assets")
        IrQweb._warm_page_assets()
        warmed = self._warmed_bundles()
        computed = []
        model = type(IrQweb)
        links = model._get_asset_links_uncached
        nodes = model._get_native_module_nodes_uncached

        def links_spy(qweb, bundle, *args, **kwargs):
            computed.append(("links", bundle))
            return links(qweb, bundle, *args, **kwargs)

        def nodes_spy(qweb, bundle, *args, **kwargs):
            computed.append(("nodes", bundle, kwargs.get("page_scope")))
            return nodes(qweb, bundle, *args, **kwargs)

        with (
            patch.object(model, "_get_asset_links_uncached", links_spy),
            patch.object(model, "_get_native_module_nodes_uncached", nodes_spy),
        ):
            self.assertEqual(self.url_open("/web/login").status_code, 200)
            self.authenticate("admin", "admin")
            self.assertEqual(self.url_open("/odoo").status_code, 200)
        self.assertTrue(
            {"web.assets_web", "web.assets_frontend_lazy"} <= warmed,
            "fixture: both the web client and the split frontend page are warmed",
        )
        self.assertEqual([call for call in computed if call[1] in warmed], [])
