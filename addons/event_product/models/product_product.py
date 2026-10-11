from odoo import api, fields, models
from odoo.exceptions import ValidationError


def raise_event_ticket_service_tracking_error(products) -> None:
    service_tracking = products.fields_get(
        ["service_tracking"], ["string", "selection"]
    )["service_tracking"]
    raise ValidationError(
        products.env._(
            'Products linked to an event ticket must have "%(tracking)s" set to '
            '"%(event)s":\n%(products)s',
            tracking=service_tracking["string"],
            event=dict(service_tracking["selection"])["event"],
            products="\n".join(f"- {name}" for name in products.mapped("display_name")),
        )
    )


class ProductProduct(models.Model):
    _inherit = "product.product"

    event_ticket_ids = fields.One2many(
        comodel_name="event.event.ticket",
        inverse_name="product_id",
        string="Event Tickets",
    )

    event_type_ticket_ids = fields.One2many(
        comodel_name="event.type.ticket",
        inverse_name="product_id",
        string="Event Template Tickets",
    )

    @api.constrains("event_ticket_ids", "event_type_ticket_ids", "service_tracking")
    def _check_event_ticket_service_tracking(self) -> None:
        bad = self.filtered(
            lambda product: (
                (product.event_ticket_ids or product.event_type_ticket_ids)
                and product.service_tracking != "event"
            )
        )
        if bad:
            raise_event_ticket_service_tracking_error(bad)
