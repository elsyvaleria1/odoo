from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProfileDialogBundle(TransactionCase):
    def _paths(self, bundle):
        IrAsset = self.env["ir.asset"]
        return [
            entry.path.lstrip("/")
            for entry in IrAsset._get_asset_paths(
                bundle, IrAsset._prepare_assets_params()
            )
        ]

    def test_the_profile_dialog_is_not_on_every_public_page(self):
        frontend = self._paths("web.assets_frontend")
        self.assertIn(
            "website_profile/static/src/interactions/profile_editor.js", frontend
        )
        self.assertFalse(
            [
                p
                for p in frontend
                if p.startswith("website_profile/static/src/components/")
            ]
        )

    def test_the_lazy_bundle_carries_the_dialog_and_its_editor(self):
        lazy = self._paths("website_profile.assets_profile_dialog")
        self.assertIn(
            "website_profile/static/src/components/profile_dialog/profile_dialog.js",
            lazy,
        )
        self.assertIn("html_editor/static/src/wysiwyg.js", lazy)
        children = {
            child.name
            for child in self.env["ir.qweb"]._get_dynamic_child_bundles(
                "web.assets_frontend", None, debug_assets=False
            )
        }
        self.assertIn("website_profile.assets_profile_dialog", children)
