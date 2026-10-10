from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request, route

from odoo.addons.sale.controllers import portal as sale_portal
from odoo.addons.website_sale.controllers.cart import ADD_TO_CART_TRACKING_KEY, Cart


class CustomerPortal(sale_portal.CustomerPortal):
    @route(
        "/my/orders/reorder",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def my_orders_reorder(self, order_id, access_token=None, **kwargs):
        try:
            sale_order = request.env["access.link"]._open_record(
                "sale.order", int(order_id), access_token=access_token
            )
        except AccessError, MissingError, ValueError:
            raise request.prepare_not_found_error() from None

        lines_to_reorder = sale_order.line_ids.filtered(
            lambda line: line.with_user(request.env.user).sudo()._is_reorder_allowed()
        )

        if not lines_to_reorder:
            raise ValidationError(
                request.env._("Nothing can be reordered in this order")
            )

        Cart_controller = Cart()
        order_sudo = request.cart or request.website._create_cart()
        warnings_to_aggregate = set()
        values = {
            "tracking_info": [],
        }
        for line in lines_to_reorder:
            cart_values = Cart_controller.add_to_cart(
                **line._prepare_reorder_cart_values(line.product_qty)
            )
            if not cart_values["quantity"]:
                warnings_to_aggregate.add(order_sudo.shop_warning)

            values["tracking_info"].extend(cart_values["tracking_info"])

        if warnings_to_aggregate:
            order_sudo.shop_warning = "\n".join(warnings_to_aggregate)

        # reported by the cart page this redirects to (@website_sale/interactions/tracking)
        request.session[ADD_TO_CART_TRACKING_KEY] = (
            request.session.get(ADD_TO_CART_TRACKING_KEY, []) + values["tracking_info"]
        )
        return request.redirect("/shop/cart")
