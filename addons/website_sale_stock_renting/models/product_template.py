from collections import defaultdict
from datetime import UTC
from math import floor

from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.http import request
from odoo.libs.datetime import timezone
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _get_default_start_date(self, pickup_time):
        start_date = super()._get_default_start_date(pickup_time)

        now = fields.Datetime.now()
        hours_before_start_date = (start_date - now).total_seconds() / 3600
        if hours_before_start_date < self.preparation_time:
            start_date = now + relativedelta(hours=self.preparation_time)
            if pickup_time:
                website_tz = timezone(request.website.tz)
                pickup_hour = floor(pickup_time)
                start_date_website_tz = start_date.replace(tzinfo=website_tz).replace(
                    hour=pickup_hour,
                    minute=round((pickup_time - pickup_hour) * 60),
                )
                start_date = start_date_website_tz.astimezone(UTC).replace(tzinfo=None)
        return start_date

    def _filter_on_available_rental_products(self, from_date, to_date, warehouse_id):
        if to_date < from_date:
            return self.filtered(lambda p: not p.rent_ok)

        products_infinite_qty = products_finite_qty = self.env["product.template"]
        for product in self:
            if (
                not product.rent_ok
                or not product.is_storable
                or product.allow_out_of_stock_order
            ):
                products_infinite_qty |= product
            else:
                products_finite_qty |= product

        if not products_finite_qty:
            return products_infinite_qty

        variants_to_check = products_finite_qty.with_context(
            from_date=from_date,
            to_date=to_date,
            warehouse_id=warehouse_id,
        ).product_variant_ids.filtered(
            lambda p: bool(p.qty_available > 0 or p.qty_in_rent > 0)
        )
        templates_with_available_qty = self.env["product.template"]
        if variants_to_check:
            search_domain = [
                ("is_rental", "=", True),
                ("product_id", "in", variants_to_check.ids),
                "|",
                ("state", "=", "done"),
                "&",
                ("state", "=", "draft"),
                ("order_id.sent", "=", True),
                ("return_date", ">", from_date),
                "|",
                ("reservation_begin", "<", to_date),
                ("qty_transferred", ">", 0),
                ("company_id", "=", self.env.company.id),
            ]
            if warehouse_id:
                search_domain.append(("order_id.warehouse_id", "=", warehouse_id))
            sols = self.env["sale.order.line"].search(
                search_domain, order="reservation_begin asc"
            )
            sol_by_variant = defaultdict(lambda: self.env["sale.order.line"])
            for sol in sols:
                sol_by_variant[sol.product_id] |= sol

            def has_any_available_qty(variant, sols) -> bool:
                rented_quantities, key_dates = sols._get_rented_quantities(
                    [from_date, to_date]
                )
                max_rentable = variant.qty_available + variant.qty_in_rent
                for date in key_dates:
                    max_rentable -= rented_quantities[date]
                    if max_rentable <= 0:
                        _debug.logic(
                            "rental_unavailable",
                            reason="no_stock_on_date",
                            variant=variant.id,
                        )
                        return False
                return True

            templates_with_available_qty = variants_to_check.filtered(
                lambda v: (
                    v not in sol_by_variant
                    or has_any_available_qty(v, sol_by_variant[v])
                )
            ).product_tmpl_id

        return products_infinite_qty | templates_with_available_qty
