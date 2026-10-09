from odoo import fields

from odoo.addons.web.controllers.utils import Fragment


def get_order_total_fragment(
    order_sudo, *, hide_promotions=False, redirect=None, code_not_available=False
) -> Fragment:
    # inner: every total on the page keeps the classes its own t-call gave it;
    # show_shorter_cart_summary: nothing renders beside the total's root;
    # redirect: the page's own, which the coupon form posts back to
    values = {
        "website_sale_order": order_sudo,
        "show_shorter_cart_summary": True,
        "hide_promotions": hide_promotions,
        "redirect": redirect,
        "code_not_available": code_not_available,
    }
    if hide_promotions:
        return Fragment(
            "website_sale.total",
            values,
            key="website_sale.total_no_promotions",
            swap="inner",
        )
    return Fragment("website_sale.total", values, swap="inner")


def get_cart_summary_fragment(order_sudo) -> Fragment:
    return Fragment(
        "website_sale.cart_summary_content", {"website_sale_order": order_sudo}
    )


def get_cart_lines_fragment(order_sudo) -> Fragment:
    return Fragment(
        "website_sale.cart_lines",
        {
            "website_sale_order": order_sudo,
            "date": fields.Date.today(),
            "suggested_products": order_sudo._cart_accessories(),
        },
    )


def get_coupon_fragments(order_sudo, redirect, code_not_available=False) -> list:
    # the cart page shows lines and a total, a checkout page a summary and both
    # totals; a page swaps those of these it has
    return [
        get_cart_lines_fragment(order_sudo),
        get_cart_summary_fragment(order_sudo),
        get_order_total_fragment(
            order_sudo, redirect=redirect, code_not_available=code_not_available
        ),
        get_order_total_fragment(order_sudo, hide_promotions=True, redirect=redirect),
    ]
