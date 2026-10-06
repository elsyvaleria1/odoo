from dateutil.relativedelta import relativedelta

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    renting_minimal_time_duration = fields.Integer(string="Minimal Rental Duration")
    renting_minimal_time_unit = fields.Selection(
        selection=[
            ("hour", "Hours"),
            ("day", "Days"),
            ("week", "Weeks"),
            ("month", "Months"),
        ],
        string="Minimal Rental Duration Unit",
        default="day",
        required=True,
    )
    renting_forbidden_mon = fields.Boolean(string="Monday")
    renting_forbidden_tue = fields.Boolean(string="Tuesday")
    renting_forbidden_wed = fields.Boolean(string="Wednesday")
    renting_forbidden_thu = fields.Boolean(string="Thursday")
    renting_forbidden_fri = fields.Boolean(string="Friday")
    renting_forbidden_sat = fields.Boolean(string="Saturday")
    renting_forbidden_sun = fields.Boolean(string="Sunday")

    def _get_minimal_rental_duration(self):
        return relativedelta(
            **{f"{self.renting_minimal_time_unit}s": self.renting_minimal_time_duration}
        )

    def _get_renting_forbidden_days(self) -> list:
        forbidden_day_fields = {
            "renting_forbidden_mon": 1,
            "renting_forbidden_tue": 2,
            "renting_forbidden_wed": 3,
            "renting_forbidden_thu": 4,
            "renting_forbidden_fri": 5,
            "renting_forbidden_sat": 6,
            "renting_forbidden_sun": 7,
        }
        return [value for field, value in forbidden_day_fields.items() if self[field]]
