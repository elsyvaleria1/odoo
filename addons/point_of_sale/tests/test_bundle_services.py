from odoo.tests import TransactionCase, tagged

from odoo.addons.web.tests.bundle_services import BundleServicesCase, sources_outside

POS_SOURCES = sources_outside("web")


@tagged("-at_install", "post_install")
class TestPosBundleServices(BundleServicesCase):
    def test_every_pos_bundle_starts_the_services_its_components_require(self):
        for bundle in (
            "point_of_sale._assets_pos",
            "point_of_sale.assets_prod",
            "point_of_sale.customer_display_assets",
        ):
            with self.subTest(bundle=bundle):
                self.assertBundleStartsRequiredServices(bundle, POS_SOURCES)


@tagged("-at_install", "post_install")
class TestPosProductionBundleCarriesNoTestHarness(TransactionCase):
    RUNNERS = (
        "web/static/lib/hoot-dom/",
        "web_tour/static/src/js/tour_automatic/",
        "web_tour/static/src/js/tour_interactive/",
        "web_tour/static/src/js/tour_recorder/tour_recorder.js",
    )

    def test_the_pos_boot_leaves_hoot_and_the_tour_runners_out(self):
        IrAsset = self.env["ir.asset"]
        paths = [
            entry.path.lstrip("/")
            for entry in IrAsset._get_asset_paths(
                "point_of_sale.assets_prod", IrAsset._prepare_assets_params()
            )
        ]
        self.assertIn("web_tour/static/src/js/tour_service.js", paths)
        shipped = sorted(p for p in paths if p.startswith(self.RUNNERS))
        self.assertEqual(shipped, [], "the POS boot ships the test/tour harness")

    def test_the_tour_runners_are_lazy_children_of_the_pos_page(self):
        children = {
            child.name
            for child in self.env["ir.qweb"]._get_dynamic_child_bundles(
                "point_of_sale.assets_prod", None, debug_assets=False
            )
        }
        self.assertLessEqual(
            {"web_tour.automatic", "web_tour.interactive", "web_tour.recorder"},
            children,
        )
