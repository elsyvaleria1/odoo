from odoo import models
from odoo.fields import Domain
from odoo.http import request


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _get_rented_quantities(self, from_date, to_date, domain=None):
        self.check_singleton()

        return (
            self.env["sale.order.line"]
            .search(
                Domain.AND(
                    [
                        domain or Domain.TRUE,
                        [
                            ("is_rental", "=", True),
                            ("product_id", "=", self.id),
                            "|",
                            ("state", "=", "done"),
                            "&",
                            ("state", "=", "draft"),
                            ("order_id.sent", "=", True),
                            ("return_date", ">", from_date),
                            "|",
                            ("reservation_begin", "<", to_date),
                            ("qty_transferred", ">", 0),
                        ],
                    ]
                ),
                order="reservation_begin asc",
            )
            ._get_rented_quantities([from_date, to_date])
        )

    def _get_availabilities(self, from_date, to_date, warehouse_id, with_cart=False):
        self.check_singleton()

        qty_available = self.with_context(
            from_date=from_date, to_date=to_date, warehouse_id=warehouse_id
        ).qty_available
        qty_available += self.with_context(warehouse_id=warehouse_id).qty_in_rent
        wh_domain = (
            [("order_id.warehouse_id", "=", warehouse_id)] if warehouse_id else []
        )
        rented_quantities, key_dates = self._get_rented_quantities(
            from_date, to_date, domain=wh_domain
        )
        cart = (with_cart and request and request.cart) or self.env["sale.order"]
        if cart:
            common_lines = cart._get_common_product_lines(self.id)
            so_rented_qties, so_key_dates = common_lines._get_rented_quantities(
                [from_date, to_date]
            )
            key_dates = list(set(so_key_dates + key_dates))
            key_dates.sort()
        current_qty_available = qty_available
        availabilities = []
        for i in range(1, len(key_dates)):
            start_dt = key_dates[i - 1]
            if start_dt > to_date:
                break
            current_qty_available -= rented_quantities[start_dt]
            if cart:
                current_qty_available -= so_rented_qties[start_dt]
            if start_dt >= from_date:
                availabilities.append(
                    {
                        "start": start_dt,
                        "end": key_dates[i],
                        "quantity_available": current_qty_available,
                    }
                )

        return availabilities
