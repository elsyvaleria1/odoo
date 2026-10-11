from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    asset_log_type = fields.Selection(
        selection="_selection_asset_log_type",
        groups="base.group_asset_manager",
        help="Kind of asset spend booked to this account. Used whenever the bill "
        "line's product category types nothing — including an account-only "
        "line with no product at all, which is where it matters most: "
        "without it the asset log lands in no bucket.",
    )

    def _selection_asset_log_type(self):
        return self.env["resource.log"]._selection_log_type()
