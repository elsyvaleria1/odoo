from odoo import Command, api, fields, models


class WizardSaleOrderUpdateAttendeeLine(models.TransientModel):
    _name = "wizard.sale.order.update.attendee.line"
    _description = "Edit Attendee Line on Sales Confirmation"
    _order = "id desc"

    editor_id = fields.Many2one(comodel_name="wizard.sale.order.update.attendee")
    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sales Order Line",
    )
    event_id = fields.Many2one(
        comodel_name="event.event",
        required=True,
    )
    company_id = fields.Many2one(related="event_id.company_id")
    registration_id = fields.Many2one(
        comodel_name="event.registration",
        string="Original Registration",
    )
    event_slot_id = fields.Many2one(comodel_name="event.slot")
    event_ticket_id = fields.Many2one(comodel_name="event.event.ticket")
    email = fields.Char()
    phone_ids = fields.Many2many(comodel_name="phone.number")
    phone_country_id = fields.Many2one(
        comodel_name="res.country",
        compute="_compute_phone_country_id",
    )
    name = fields.Char()

    @api.depends("editor_id.sale_order_id.partner_id.country_id", "event_id.country_id")
    def _compute_phone_country_id(self) -> None:
        for line in self:
            line.phone_country_id = (
                line.editor_id.sale_order_id.partner_id.country_id
                or line.event_id.country_id
            )

    def _prepare_registration_data(self, include_event_values=False):
        self.check_singleton()
        registration_data = {
            "partner_id": self.editor_id.sale_order_id.partner_id.id,
            "name": self.name or self.editor_id.sale_order_id.partner_id.name,
            "phone_ids": [
                Command.set(
                    (
                        self.phone_ids
                        or self.editor_id.sale_order_id.partner_id.phone_ids._primary()
                    ).ids
                )
            ],
            "email": self.email or self.editor_id.sale_order_id.partner_id.email,
        }
        if include_event_values:
            registration_data.update(
                {
                    "event_id": self.event_id.id,
                    "event_slot_id": self.event_slot_id.id,
                    "event_ticket_id": self.event_ticket_id.id,
                    "sale_order_id": self.editor_id.sale_order_id.id,
                    "sale_order_line_id": self.sale_order_line_id.id,
                }
            )
        return registration_data
