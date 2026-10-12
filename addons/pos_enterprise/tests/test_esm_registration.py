from odoo.tests.common import TransactionCase, tagged
from odoo.tools.assets.esm_registry import esm_registry


@tagged("post_install", "-at_install")
class TestEsmRegistration(TransactionCase):
    PRIMARY = "pos_preparation_display.assets"
    TOURS = "pos_preparation_display.assets_tour_tests"

    def test_prep_display_bundles_are_registered(self):
        bundles = esm_registry().bundles
        self.assertIn(self.PRIMARY, bundles)
        self.assertIn(self.TOURS, bundles)

    def test_tour_bundle_is_secondary_not_import_map_include(self):
        reg = esm_registry()
        self.assertIn(self.TOURS, reg.secondary_import_map_includes[self.PRIMARY])
        self.assertNotIn(self.TOURS, reg.import_map_includes.get(self.PRIMARY, ()))
        self.assertNotIn(self.TOURS, reg.import_map_included_bundles)

    def test_the_bundles_belong_to_this_module(self):
        registry = esm_registry()
        installed = self.env["ir.asset"]._get_addons_installed()
        for name in (self.PRIMARY, self.TOURS):
            self.assertEqual(registry.bundle_addon(name), "pos_enterprise")
            self.assertIn(registry.bundle_addon(name), installed)
        self.assertNotIn("pos_preparation_display", installed)

    def test_secondary_parents_resolves_the_app_bundle(self):
        self.assertEqual(esm_registry().secondary_parents[self.TOURS], (self.PRIMARY,))
