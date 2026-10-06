from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    commission_automatic_po_frequency = fields.Selection(
        selection=[
            ("manually", "Manually"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
        ],
        default="monthly",
        required=True,
    )
    commission_po_minimum = fields.Monetary(
        string="Minimum Total Amount for PO commission",
        currency_field="currency_id",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    commission_automatic_po_frequency = fields.Selection(
        related="company_id.commission_automatic_po_frequency",
        readonly=False,
        required=True,
    )
    commission_po_minimum = fields.Monetary(
        related="company_id.commission_po_minimum",
        string="Minimum Total Amount for PO commission",
        currency_field="currency_id",
        readonly=False,
    )
