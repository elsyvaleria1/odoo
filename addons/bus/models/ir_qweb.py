from odoo import models

WORKER_BUNDLE = "bus.websocket_worker_assets"


class IrQWeb(models.AbstractModel):
    _inherit = "ir.qweb"

    def _get_websocket_worker_bundle(self):
        return self._get_standalone_bundle(WORKER_BUNDLE)

    def _get_websocket_worker_sources(self):
        assets = self.env["ir.asset"]
        return {
            asset.path.lstrip("/"): asset.full_path
            for asset in assets._get_asset_paths(
                WORKER_BUNDLE, assets._prepare_assets_params()
            )
            if not asset.is_external and asset.path.endswith(".js")
        }

    def _pregenerate_assets_bundles(self):
        links = super()._pregenerate_assets_bundles()
        result = self._get_websocket_worker_bundle()
        if result:
            links.append(result[0])
        return links
