from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class ApprovalRequestLine(models.Model):
    _inherit = "approval.request.line"
    _access_anchors = frozendict(
        {
            "approval_request_approver_delegate": models.Anchor(
                "approval_request_id.approver_ids.delegate_id", kind="owner"
            ),
            "approval_request_approver_user": models.Anchor(
                "approval_request_id.approver_ids.user_id", kind="owner"
            ),
            "approval_request_category_allowed_group_all_user": models.Anchor(
                "approval_request_id.category_id.allowed_group_ids.all_user_ids",
                kind="owner",
            ),
            "approval_request_category_allowed_user": models.Anchor(
                "approval_request_id.category_id.allowed_user_ids", kind="owner"
            ),
            "owner": "approval_request_id.request_owner_id",
        }
    )

    stock_move_id = fields.Many2one(
        comodel_name="stock.move",
        index=True,
        copy=False,
        readonly=True,
        help="Link to the stock move created from this approval line",
    )
    stock_picking_id = fields.Many2one(
        comodel_name="stock.picking",
        related="stock_move_id.picking_id",
        readonly=True,
        help="Stock picking that contains the move created from this approval",
    )
    location_id = fields.Many2one(
        comodel_name="stock.location",
        help="Source location for stock move",
    )
    location_dest_id = fields.Many2one(
        comodel_name="stock.location",
        help="Destination location for stock move",
    )
    picking_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        help="Type of stock operation (Receipt, Delivery, Internal Transfer)",
    )

    def _get_fields_line_system(self) -> frozenset[str]:
        return super()._get_fields_line_system() | {"stock_move_id"}

    def _format_lines_for_error(self) -> str:
        return "\n".join(
            self.env._(
                "• line %(line_id)s (product: %(product)s)",
                line_id=line.id,
                product=line.product_id.display_name or line.description,
            )
            for line in self
        )

    def _check_locations(self) -> None:
        _debug.logic("approval_line_locations_check", lines=self)
        lines_without_locations = self.filtered(
            lambda line: not line.location_id or not line.location_dest_id
        )
        if lines_without_locations:
            raise UserError(
                self.env._(
                    "These lines are missing a source or destination location. "
                    "Please set locations on all of them before creating stock "
                    "transfers:\n\n%(lines)s",
                    lines=lines_without_locations._format_lines_for_error(),
                )
            )

    def _check_picking_type(self) -> None:
        _debug.logic("approval_line_picking_type_check", lines=self)
        lines_without_type = self.filtered(lambda line: not line.picking_type_id)
        if lines_without_type:
            raise UserError(
                self.env._(
                    "These lines are missing an operation type. Please set one "
                    "on all of them before creating stock "
                    "transfers:\n\n%(lines)s",
                    lines=lines_without_type._format_lines_for_error(),
                )
            )
