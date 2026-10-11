from odoo import api, fields, models


class AutomationRule(models.Model):

    _inherit = "automation.rule"

    trg_date_resource_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Use employee work schedule",
        help="Use the user's working schedule.",
    )

    @api.model
    def _get_calendar(self, automation, record):
        if (
            automation.trg_date_range_type == "day"
            and automation.trg_date_resource_field_id
        ):
            user = record[automation.trg_date_resource_field_id.name]
            calendar = user.employee_id.version_id.resource_calendar_id
            if calendar:
                return calendar
        return super()._get_calendar(automation, record)
