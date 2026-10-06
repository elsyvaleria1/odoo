from odoo import models
from odoo.fields import Domain


class StockLocation(models.Model):
    _inherit = "stock.location"

    def _get_domains_quantity(self, location_ids):
        # Was an override of `product.product._get_domain_locations_new`; the scope
        # moved to the model whose records it is about.
        domain_quant, domain_move_in_loc, domain_move_out_loc = (
            super()._get_domains_quantity(location_ids)
        )
        if self.env.context.get("ignore_rental_returns"):
            rental_loc_ids = self.env.companies.rental_loc_id.ids
            domain_move_in_loc &= Domain("location_id", "not in", rental_loc_ids)
        return domain_quant, domain_move_in_loc, domain_move_out_loc
