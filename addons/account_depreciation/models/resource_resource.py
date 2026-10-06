from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    value_original = fields.Monetary(
        compute="_compute_value_original",
        store=True,
        readonly=False,
    )
    date_acquisition = fields.Date(
        compute="_compute_date_acquisition",
        store=True,
        copy=True,
        readonly=False,
    )
    date_disposal = fields.Date(
        compute="_compute_date_disposal",
        store=True,
        readonly=False,
    )

    @api.depends(
        "asset_id.board_id.original_move_line_ids",
        "asset_id.board_id.original_move_line_ids.account_id",
        "asset_id.board_id.value_non_deductible_tax",
    )
    @_debug.perf.timed
    def _compute_value_original(self) -> None:
        for resource in self:
            board = resource.asset_id.board_id
            if not board.original_move_line_ids:
                continue
            resource.value_original = board._get_value_original_from_lines()

    @api.depends("asset_id.board_id.original_move_line_ids")
    def _compute_date_acquisition(self) -> None:
        for resource in self:
            board = resource.asset_id.board_id
            if not board:
                resource.date_acquisition = resource.date_acquisition
                continue
            resource.date_acquisition = (
                resource.date_acquisition or board._get_date_acquisition_default()
            )

    @api.depends(
        "asset_id.board_id.depreciation_move_ids.date",
        "asset_id.board_id.depreciation_state",
    )
    def _compute_date_disposal(self) -> None:
        for resource in self:
            board = resource.asset_id.board_id
            if board.depreciation_state == "close":
                dates = board.depreciation_move_ids.filtered(
                    lambda m: m.date and m.state != "cancel"
                ).mapped("date")
                resource.date_disposal = (
                    max([*dates, resource.date_acquisition or dates[0]])
                    if dates
                    else resource.date_disposal
                    or resource.date_acquisition
                    or fields.Date.context_today(resource)
                )
            elif board:
                resource.date_disposal = False
            else:
                resource.date_disposal = resource.date_disposal
