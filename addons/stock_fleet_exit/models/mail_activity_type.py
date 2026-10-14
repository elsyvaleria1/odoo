from odoo import fields, models


class MailActivityType(models.Model):
    _inherit = "mail.activity.type"

    fleet_exit_role = fields.Selection(
        selection=[
            ("destination", "Route Activity"),
            ("authorisation", "Route Authorisation"),
        ],
        help="Route Activity: what a vehicle route goes to do, offered to the "
        "driver by /rutas. Route Authorisation: what an authoriser decides before "
        "the vehicle leaves.",
    )
    fleet_exit_group = fields.Char(
        string="Route Group",
        translate=True,
        help="Route activities sharing a group are offered together under it: "
        "Errand for Water and Garbage, Dealership for Toyota.",
    )

    def _get_exit_label(self) -> str:
        self.check_singleton()
        if self.fleet_exit_group:
            return f"{self.fleet_exit_group} / {self.name}"
        return self.name
