from odoo.http import request, route

from .main import add_product_to_wishlist
from odoo.addons.web.controllers.utils import fragments_or_redirect
from odoo.addons.website_sale.controllers.cart import Cart


class WishlistCart(Cart):
    @route(
        "/shop/wishlist/save_for_later",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
        sitemap=False,
    )
    def save_for_later(self, line_id=None, **kwargs):
        order_sudo = request.cart
        line = order_sudo.line_ids.filtered(lambda sol: str(sol.id) == str(line_id))
        values, saved = {}, {}
        if line and line._is_sellable():
            product = line.product_id
            if product not in request.env["product.wishlist"].current().product_id:
                add_product_to_wishlist(product)
            values = order_sudo._cart_update_line_quantity(line.id, 0)
            saved = {"website_sale_wishlist:product_added": {"product_id": product.id}}
        fragments, changes = self._cart_changed(order_sudo, values)
        changes["events"] = {**changes["events"], **saved}
        return fragments_or_redirect(request.env, "/shop/cart", *fragments, **changes)
