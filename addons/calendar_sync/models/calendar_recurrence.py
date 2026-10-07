from odoo import fields, models


class CalendarRecurrence(models.Model):
    _name = "calendar.recurrence"
    _inherit = ["calendar.recurrence", "mixin.calendar.sync"]

    calendar_sync_link_ids = fields.One2many(
        comodel_name="calendar.sync.link",
        inverse_name="recurrence_id",
        string="Calendar Synchronization Links",
        classification="calendar_sync.state",
        groups="base.group_system",
    )
