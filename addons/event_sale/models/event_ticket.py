from odoo import models


class EventEventTicket(models.Model):
    _inherit = "event.event.ticket"
    _order = "event_id, sequence, price, name, id"

    def _get_ticket_multiline_description(self):
        self.check_singleton()
        if self.product_id.description_sale:
            return "%s\n%s" % (
                self.product_id.description_sale,
                self.event_id.display_name,
            )
        return super()._get_ticket_multiline_description()
