from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestChatterAssets(TransactionCase):
    BUNDLE = "portal.assets_chatter"

    def test_the_chatter_inlines_no_module_its_page_does_not_carry(self):
        IrQweb = self.env["ir.qweb"]
        params = self.env["ir.asset"]._prepare_assets_params()
        chatter = IrQweb._get_asset_bundle(self.BUNDLE, css=False, js=True)
        parent_specs = IrQweb._get_runtime_parent_specs(
            IrQweb._get_runtime_group_parents(self.BUNDLE), params
        )
        self.assertTrue(parent_specs, "fixture: the chatter has a page")
        with self.assertNoLogs("odoo.assets.fallback", "WARNING"):
            IrQweb._get_runtime_child_own_modules(self.BUNDLE, chatter, parent_specs)
