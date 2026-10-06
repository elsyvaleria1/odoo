from unittest.mock import patch

from odoo.cli.command import commands, load_internal_commands
from odoo.cli.warm_assets import warm_asset_bundles
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWarmAssets(TransactionCase):
    def test_the_command_is_registered(self):
        load_internal_commands()
        self.assertIn("warm_assets", commands)

    def test_every_website_variant_is_built(self):
        second = self.env["website"].create({"name": "Warm probe"})
        seen = []

        def pregenerate(qweb):
            seen.append(qweb.env.context.get("website_id"))
            return [f"/url/{len(seen)}"]

        with patch.object(
            type(self.env["ir.qweb"]), "_pregenerate_assets_bundles", pregenerate
        ):
            links = warm_asset_bundles(self.env)
        websites = self.env["website"].search([])
        self.assertIn(second, websites)
        self.assertEqual(seen, [None, *websites.ids])
        self.assertEqual(len(links), len(seen))
