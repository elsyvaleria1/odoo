from odoo import fields, models


class EventTypeMail(models.Model):
    _name = "event.type.mail"
    _inherit = ["mixin.event.mail.schedule"]
    _description = "Mail Scheduling on Event Category"

    event_type_id = fields.Many2one(
        comodel_name="event.type",
        required=True,
        ondelete="cascade",
    )
