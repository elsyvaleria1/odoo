from odoo import fields, models


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    visitor_id = fields.Many2one(
        comodel_name="website.visitor",
        index="btree_not_null",
        ondelete="set null",
    )
