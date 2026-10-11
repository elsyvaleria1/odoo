from odoo import fields, models
from odoo.tools import frozendict


class CalendarFilters(models.Model):
    _name = "calendar.filters"
    _description = "Calendar Filters"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Me",
        default=lambda self: self.env.user,
        index=True,
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Employee",
        index=True,
        required=True,
        ondelete="cascade",
    )
    active = fields.Boolean(default=True)
    partner_checked = fields.Boolean(
        string="Checked",
        default=True,
    )

    _user_id_partner_id_unique = models.Constraint(
        "UNIQUE(user_id, partner_id)",
        "A user cannot have the same contact twice.",
    )
