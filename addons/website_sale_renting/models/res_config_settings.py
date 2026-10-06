from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    renting_minimal_time_duration = fields.Integer(
        related="company_id.renting_minimal_time_duration",
        readonly=False,
    )
    renting_minimal_time_unit = fields.Selection(
        related="company_id.renting_minimal_time_unit",
        readonly=False,
        required=True,
    )
    renting_forbidden_mon = fields.Boolean(
        related="company_id.renting_forbidden_mon",
        string="Monday",
        readonly=False,
    )
    renting_forbidden_tue = fields.Boolean(
        related="company_id.renting_forbidden_tue",
        string="Tuesday",
        readonly=False,
    )
    renting_forbidden_wed = fields.Boolean(
        related="company_id.renting_forbidden_wed",
        string="Wednesday",
        readonly=False,
    )
    renting_forbidden_thu = fields.Boolean(
        related="company_id.renting_forbidden_thu",
        string="Thursday",
        readonly=False,
    )
    renting_forbidden_fri = fields.Boolean(
        related="company_id.renting_forbidden_fri",
        string="Friday",
        readonly=False,
    )
    renting_forbidden_sat = fields.Boolean(
        related="company_id.renting_forbidden_sat",
        string="Saturday",
        readonly=False,
    )
    renting_forbidden_sun = fields.Boolean(
        related="company_id.renting_forbidden_sun",
        string="Sunday",
        readonly=False,
    )
    tz = fields.Selection(
        related="website_id.tz",
        readonly=False,
    )
