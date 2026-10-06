from odoo import api, models
from odoo.tools import SQL


class AccountDeferredReportHandler(models.AbstractModel):
    _inherit = "account.deferred.report.handler"

    @api.model
    def _get_select(self, options):
        return super()._get_select(options) + [
            SQL("account_move_line.asset_id AS asset_id")
        ]

    @api.model
    def _get_grouping_fields_deferred_lines(
        self, filter_already_generated=False, grouping_field="account_id"
    ):
        res = super()._get_grouping_fields_deferred_lines(
            filter_already_generated, grouping_field
        )
        if filter_already_generated:
            res += ("asset_id",)
        return res

    @api.model
    def _get_grouping_fields_deferral_lines(self):
        res = super()._get_grouping_fields_deferral_lines()
        res += ("asset_id",)
        return res

    @api.model
    def _get_current_key_totals_dict(self, lines_per_key, sign):
        totals = super()._get_current_key_totals_dict(lines_per_key, sign)
        totals["asset_id"] = lines_per_key[0]["asset_id"]
        return totals
