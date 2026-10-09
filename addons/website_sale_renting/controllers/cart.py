from odoo import fields
from odoo.http import request, route

from odoo.addons.web.controllers.utils import FragmentResponse, render_fragments
from odoo.addons.website_sale.controllers.cart import Cart as WebsiteSaleCart


class Cart(WebsiteSaleCart):
    @route(
        "/shop/cart/update_renting",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def update_cart_renting(
        self, start_date=None, end_date=None
    ) -> FragmentResponse | None:
        try:
            start_date = fields.Datetime.to_datetime(start_date)
            end_date = fields.Datetime.to_datetime(end_date)
        except ValueError:
            start_date = end_date = None
        if not (start_date and end_date and (order_sudo := request.cart)):
            return None
        order_sudo._cart_update_renting_period(start_date, end_date)
        return render_fragments(
            request.env,
            self._get_cart_lines_fragment(order_sudo),
            self._get_cart_total_fragment(order_sudo),
            events=self._cart_updated_events(order_sudo),
            data={
                "cart_quantity": order_sudo.cart_quantity,
                "cart_ready": order_sudo._is_cart_ready(),
                "start_date": order_sudo.rental_start_date,
                "end_date": order_sudo.rental_return_date,
            },
        )

    @route()
    def add_to_cart(self, *args, start_date=None, end_date=None, **kwargs):
        start_date = fields.Datetime.to_datetime(start_date)
        end_date = fields.Datetime.to_datetime(end_date)
        return super().add_to_cart(
            *args, start_date=start_date, end_date=end_date, **kwargs
        )
