from odoo import fields, models


class HelpdeskSla(models.Model):
    _inherit = "helpdesk.sla"

    product_ids = fields.Many2many(
        comodel_name="product.template",
        string="Services",
        domain="[('sale_ok', '=', True), ('type', '=', 'service')]",
    )
    use_helpdesk_sale_timesheet = fields.Boolean(
        related="team_id.use_helpdesk_sale_timesheet"
    )
