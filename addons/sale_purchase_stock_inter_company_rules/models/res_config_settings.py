from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    intercompany_warehouse_id = fields.Many2one(
        related="company_id.intercompany_warehouse_id",
        string="Warehouse For Purchase Orders",
        readonly=False,
        domain=lambda self: [("company_id", "=", self.env.company.id)],
    )
    intercompany_receipt_type_id = fields.Many2one(
        related="company_id.intercompany_receipt_type_id",
        readonly=False,
        domain=lambda self: [
            ("warehouse_id", "=", self.company_id.intercompany_warehouse_id.id),
            ("code", "=", "incoming"),
        ],
    )
    intercompany_sync_delivery_receipt = fields.Boolean(
        related="company_id.intercompany_sync_delivery_receipt",
        string="Synchronize Stock Moves",
        readonly=False,
    )
