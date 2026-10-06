from odoo import api, fields, models


class HrVersion(models.Model):
    _name = "hr.version"
    _inherit = ["hr.version", "mixin.analytic"]
    _description = "Employee Contract"

    analytic_distribution = fields.Json(
        tracking=False,
        groups="hr.group_hr_user",
    )
    analytic_precision = fields.Integer(
        tracking=False,
        groups="hr.group_hr_user",
    )
    distribution_analytic_account_ids = fields.Many2many(
        tracking=False,
        groups="hr.group_hr_user",
    )

    @api.model
    def _get_whitelist_fields_from_template(self):
        return super()._get_whitelist_fields_from_template() + ["analytic_distribution"]
