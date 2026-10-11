from odoo import fields, models


class EventRegistration(models.Model):
    _inherit = "event.registration"

    event_begin_date = fields.Datetime(store=True)
