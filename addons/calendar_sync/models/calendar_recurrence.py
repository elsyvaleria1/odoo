from odoo import fields, models


class CalendarRecurrence(models.Model):
    _inherit = "calendar.recurrence"

    calendar_sync_link_ids = fields.One2many(
        comodel_name="calendar.sync.link",
        inverse_name="recurrence_id",
        string="Calendar Synchronization Links",
        classification="calendar_sync.state",
        groups="base.group_system",
    )
