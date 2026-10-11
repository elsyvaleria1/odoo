from odoo import fields, models


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    shipment_picking_ids = fields.Many2many(
        comodel_name="stock.picking",
        relation="approval_request_shipment_picking_rel",
        column1="request_id",
        column2="picking_id",
        string="Shipped Transfers",
        check_company=True,
        help="The delivery orders this freight paid for.",
    )
