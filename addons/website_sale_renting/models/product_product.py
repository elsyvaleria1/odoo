from odoo import models
from odoo.http import request
from odoo.libs.datetime import timezone


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _can_show_website_quick_add(self) -> bool:
        return (
            super()._can_show_website_quick_add()
            and self._can_be_added_to_current_cart()
        )

    def _is_add_to_cart_allowed(self) -> bool:
        return bool(
            super()._is_add_to_cart_allowed() and self._can_be_added_to_current_cart()
        )

    def _can_be_added_to_current_cart(self) -> bool:

        if (
            not self.rent_ok
            or not (cart := request.cart)
            or not (cart.rental_start_date and cart.rental_return_date)
        ):
            return True

        if cart.line_ids.filtered("is_rental").product_id == self:
            return True

        best_pricing = self._get_best_pricing_rule(
            start_date=cart.rental_start_date,
            end_date=cart.rental_return_date,
            pricelist=request.pricelist,
            currency=request.website.currency_id,
        )
        pricing_recurrence = best_pricing.recurrence_id
        if not pricing_recurrence or not pricing_recurrence.overnight:
            return True

        website_tz = timezone(request.website.tz)
        pickup_time, return_time = (
            pricing_recurrence.pickup_time,
            pricing_recurrence.return_time,
        )
        pickup_date, return_date = (
            cart.rental_start_date.astimezone(website_tz),
            cart.rental_return_date.astimezone(website_tz),
        )

        return (
            pickup_date.hour * 60 + pickup_date.minute == round(pickup_time * 60)
            and return_date.hour * 60 + return_date.minute == round(return_time * 60)
            and pickup_date.day != return_date.day
        )
