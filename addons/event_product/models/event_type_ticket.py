import logging

from odoo import api, fields, models

from odoo.addons.event_product.models.product_product import (
    raise_event_ticket_service_tracking_error,
)
from odoo.addons.product.models.product_template import PRICE_CONTEXT_KEYS

_logger = logging.getLogger(__name__)


class EventTypeTicket(models.Model):
    _inherit = "event.type.ticket"
    _order = "sequence, price, name, id"

    def _default_product_id(self):
        return self.env.ref(
            "event_product.product_product_event", raise_if_not_found=False
        )

    description = fields.Text(
        compute="_compute_description",
        store=True,
        readonly=False,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        default=lambda self: self._default_product_id(),
        index=True,
        required=True,
        domain=[("service_tracking", "=", "event")],
    )
    currency_id = fields.Many2one(
        related="product_id.currency_id",
        string="Currency",
    )
    price = fields.Float(
        min_display_digits="Product Price",
        compute="_compute_price",
        store=True,
        readonly=False,
    )
    price_reduce = fields.Float(
        min_display_digits="Product Price",
        compute="_compute_price_reduce",
        compute_sudo=True,
    )

    @api.constrains("product_id")
    def _check_event_ticket_service_tracking(self) -> None:
        for ticket in self:
            if ticket.product_id and ticket.product_id.service_tracking != "event":
                raise_event_ticket_service_tracking_error(ticket.product_id)

    @api.depends("product_id")
    def _compute_price(self) -> None:
        for ticket in self:
            if ticket.product_id.lst_price:
                ticket.price = ticket.product_id.lst_price

    @api.depends("product_id")
    def _compute_description(self) -> None:
        for ticket in self:
            if ticket.product_id and ticket.product_id.description_sale:
                ticket.description = ticket.product_id.description_sale
            if not ticket.description:
                ticket.description = False

    @api.depends_context(*PRICE_CONTEXT_KEYS)
    @api.depends("product_id", "price")
    def _compute_price_reduce(self) -> None:
        for ticket in self:
            contextual_discount = ticket.product_id._get_contextual_discount()
            ticket.price_reduce = (1.0 - contextual_discount) * ticket.price

    def _init_column(self, column_name, *, new_column=False):
        if column_name != "product_id":
            return super()._init_column(column_name, new_column=new_column)

        self.env.cr.execute("SELECT id FROM %s WHERE product_id IS NULL" % self._table)
        ticket_type_ids = [row[0] for row in self.env.cr.fetchall()]
        if not ticket_type_ids:
            return None

        _logger.debug(
            "Table '%s': setting default value of new column %s to unique values for each row",
            self._table,
            column_name,
        )
        default_event_product = self.env.ref(
            "event_product.product_product_event", raise_if_not_found=False
        )
        if default_event_product:
            product_id = default_event_product.id
        else:
            product_id = (
                self.env["product.product"]
                .create(
                    {
                        "name": "Generic Registration Product",
                        "list_price": 0,
                        "standard_price": 0,
                        "type": "service",
                    }
                )
                .id
            )
            self.env["ir.model.data"].create(
                {
                    "name": "product_product_event",
                    "module": "event_product",
                    "model": "product.product",
                    "res_id": product_id,
                }
            )
        self.env.cr.execute(
            f"UPDATE {self._table} SET product_id = %s WHERE id = ANY(%s);",
            (product_id, ticket_type_ids),
        )
        return None

    @api.model
    def _get_event_ticket_fields_whitelist(self):
        return super()._get_event_ticket_fields_whitelist() + ["product_id", "price"]
