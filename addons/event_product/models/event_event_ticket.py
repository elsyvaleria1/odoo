from odoo import api, fields, models

from odoo.addons.product.models.product_template import PRICE_CONTEXT_KEYS


class EventEventTicket(models.Model):
    _inherit = "event.event.ticket"
    _order = "event_id, sequence, price, name, id"

    price_reduce_taxinc = fields.Float(
        string="Price Reduce Tax inc",
        compute="_compute_price_reduce_taxinc",
        compute_sudo=True,
    )
    price_incl = fields.Float(
        string="Price include",
        min_display_digits="Product Price",
        compute="_compute_price_incl",
        compute_sudo=True,
    )

    @api.depends("product_id.active")
    def _compute_sale_available(self) -> None:
        inactive_product_tickets = self.filtered(
            lambda ticket: not ticket.product_id.active
        )
        for ticket in inactive_product_tickets:
            ticket.sale_available = False
        super(
            EventEventTicket, self - inactive_product_tickets
        )._compute_sale_available()

    def _tax_included(self, amount, currency):
        self.check_singleton()
        taxes = self.product_id.taxes_id.filtered_domain(
            self.env["account.tax"]._check_company_domain(self.event_id.company_id)
        )
        return taxes.compute_all(amount, currency, 1.0, product=self.product_id)[
            "total_included"
        ]

    @api.depends_context(*PRICE_CONTEXT_KEYS)
    @api.depends(
        "price_reduce", "product_id", "product_id.taxes_id", "event_id.company_id"
    )
    def _compute_price_reduce_taxinc(self) -> None:
        for ticket in self:
            ticket.price_reduce_taxinc = ticket._tax_included(
                ticket.price_reduce, ticket.event_id.company_id.currency_id
            )

    @api.depends("product_id", "product_id.taxes_id", "price", "event_id.company_id")
    def _compute_price_incl(self) -> None:
        for ticket in self:
            if ticket.product_id and ticket.price:
                ticket.price_incl = ticket._tax_included(
                    ticket.price, ticket.event_id.company_id.currency_id
                )
            else:
                ticket.price_incl = 0
