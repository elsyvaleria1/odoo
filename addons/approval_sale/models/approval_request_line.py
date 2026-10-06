from odoo import fields, models


class ApprovalRequestLine(models.Model):
    _inherit = "approval.request.line"

    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        index=True,
        copy=False,
        readonly=True,
        help="Link to the sale order line created from this approval line",
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        related="sale_order_line_id.order_id",
        readonly=True,
        help="Sale order that contains the line created from this approval",
    )

    def _get_fields_line_system(self) -> frozenset[str]:
        return super()._get_fields_line_system() | {"sale_order_line_id"}
