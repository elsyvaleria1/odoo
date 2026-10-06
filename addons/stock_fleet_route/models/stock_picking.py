import re
from urllib.parse import quote

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    trip_eta = fields.Datetime(
        string="Estimated Arrival",
        copy=False,
        readonly=True,
        help="When the trip's vehicle should reach this customer, from the route "
        "with traffic and the service time of the previous stops.",
    )
    trip_eta_notified = fields.Datetime(
        string="Arrival Told to the Seller",
        copy=False,
        readonly=True,
        help="The arrival the seller last heard of: a delay is measured against it.",
    )

    def _route_seller(self):
        """The user who sold this delivery: the order's salesperson or the
        customer's."""
        self.check_singleton()
        return self.sale_id.user_id or self.partner_id.user_id

    def _route_customer_phone_digits(self):
        """The customer's number as WhatsApp wants it, or an empty string."""
        self.check_singleton()
        partner = self.partner_id
        number = partner._phone_get_number(
            "mobile"
        ) or partner.commercial_partner_id._phone_get_number("mobile")
        digits = re.sub(r"\D", "", number.sanitized or number.number or "")
        if len(digits) == 10:
            digits = f"52{digits}"
        return digits

    def _route_whatsapp_url(self, text) -> str:
        """Click-to-chat link that opens WhatsApp on the customer with ``text``."""
        digits = self._route_customer_phone_digits()
        if not digits:
            return ""
        return f"https://wa.me/{digits}?text={quote(text)}"
