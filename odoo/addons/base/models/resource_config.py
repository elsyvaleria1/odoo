from odoo import fields, models


class ResourceConfig(models.Model):
    _name = "resource.config"
    _description = "A company's resource configuration"
    _inherit = ["mixin.company.config"]

    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Default Working Hours",
        ondelete="restrict",
        check_company=True,
    )
    week_start = fields.Selection(
        selection=[
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ],
        string="Week Starts On",
        default="0",
        required=True,
        help="The day a flexible schedule's weekly hours start over.",
    )
