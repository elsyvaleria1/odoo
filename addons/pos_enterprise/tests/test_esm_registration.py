from odoo.tests.common import TransactionCase, tagged
from odoo.tools.assets.esm_registry import esm_registry

# No negative test here on purpose (§6.8 covers constraints, ACLs and
# workflows, none of which a manifest declaration has). The failure paths of
# check_esm_config belong to core and are already pinned there, message and
# all, by test_assetsbundle/tests/test_esm_bundles.py.


@tagged("post_install", "-at_install")
class TestEsmRegistration(TransactionCase):
    """Preparation-display bundles are declared ESM by this module."""

    PRIMARY = "pos_preparation_display.assets"
    TOURS = "pos_preparation_display.assets_tour_tests"

    def test_prep_display_bundles_are_registered(self):
        """Both bundles of the preparation-display page are ESM."""
        # The bundle namespace still carries the old module name because
        # upstream folded pos_preparation_display into pos_enterprise; the
        # module is gone but the bundles kept their names.
        bundles = esm_registry().bundles
        self.assertIn(self.PRIMARY, bundles)
        self.assertIn(self.TOURS, bundles)

    def test_tour_bundle_is_secondary_not_import_map_include(self):
        """The tour bundle shares the app's singletons instead of copying them."""
        # Both keys silence the console.error stub, so the difference is
        # invisible at a glance. An import_map_includes child is not compiled at
        # all — EsbuildCompiler.compile returns early when _import_map_included
        # is set — while the secondary key both compiles the satellite and
        # populates secondary_parents, which is what aliases its shared
        # specifiers onto the app's odoo.loader.modules instances. Neither
        # raises, so the wrong one surfaces only as a tour step that times out.
        reg = esm_registry()
        self.assertIn(self.TOURS, reg.secondary_import_map_includes[self.PRIMARY])
        self.assertNotIn(self.TOURS, reg.import_map_includes.get(self.PRIMARY, ()))
        self.assertNotIn(self.TOURS, reg.import_map_included_bundles)

    def test_the_bundles_belong_to_this_module(self):
        """The pipeline asks the registry, not the bundle prefix, whose bundle it is."""
        # `pos_preparation_display` is no installed module; a prefix check
        # dropped both bundles from every "is it installed" filter, and the
        # app bundle then registered nothing for the tour bundle's stubs
        registry = esm_registry()
        installed = self.env["ir.asset"]._get_addons_installed()
        for name in (self.PRIMARY, self.TOURS):
            self.assertEqual(registry.bundle_addon(name), "pos_enterprise")
            self.assertIn(registry.bundle_addon(name), installed)
        self.assertNotIn("pos_preparation_display", installed)

    def test_secondary_parents_resolves_the_app_bundle(self):
        """secondary_parents is the mapping the esbuild alias step reads."""
        self.assertEqual(esm_registry().secondary_parents[self.TOURS], (self.PRIMARY,))
