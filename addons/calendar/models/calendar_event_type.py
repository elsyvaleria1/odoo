from odoo import models


class CalendarEventType(models.Model):
    _name = "calendar.event.type"
    _description = "Event Meeting Type"
    _inherit = ["mixin.tag"]
