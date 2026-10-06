from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _prepare_move_for_asset_depreciation(self, vals):
        move_vals = super()._prepare_move_for_asset_depreciation(vals)
        asset = vals["asset_id"].asset_id
        vehicle = (
            asset
            if asset.kind_code == "vehicle"
            else asset.parent_id.filtered(lambda asset: asset.kind_code == "vehicle")
        )
        if vehicle:
            for _command, _id, line_vals in move_vals["line_ids"]:
                line_vals["asset_id"] = vehicle.id
        return move_vals
