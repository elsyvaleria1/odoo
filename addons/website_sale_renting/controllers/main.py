from odoo import fields
from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleRenting(WebsiteSale):
    def _get_search_options(self, **post):
        options = super()._get_search_options(**post)
        options.update(
            {
                "from_date": post.get("start_date"),
                "to_date": post.get("end_date"),
                "rent_only": post.get("rent_only") in ("True", "true", "1"),
            }
        )
        return options

    def _shop_get_query_url_kwargs(self, search, min_price, max_price, **kwargs):
        result = super()._shop_get_query_url_kwargs(
            search, min_price, max_price, **kwargs
        )
        result.update(
            start_date=kwargs.get("start_date"),
            end_date=kwargs.get("end_date"),
        )
        return result

    @route()
    def product(self, *args, start_date=None, end_date=None, **kwargs):
        if start_date and end_date:
            start_date = fields.Datetime.to_datetime(start_date)
            end_date = fields.Datetime.to_datetime(end_date)
            request.update_context(start_date=start_date, end_date=end_date)
        return super().product(
            *args, start_date=start_date, end_date=end_date, **kwargs
        )

    @route(
        "/rental/product/constraints",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        website=True,
        readonly=True,
    )
    def renting_product_constraints(self):
        weekdays = request.env.company._get_renting_forbidden_days()
        return {
            "renting_unavailabity_days": {day: day in weekdays for day in range(1, 8)},
            "renting_minimal_time": {
                "duration": request.env.company.renting_minimal_time_duration,
                "unit": request.env.company.renting_minimal_time_unit,
            },
            "website_tz": request.website.tz,
        }

    @route(
        "/rental/product/availabilities",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def renting_product_availabilities(self, product_id, min_date, max_date):
        return {}

    def _prepare_additional_shop_context(
        self, values, start_date=None, end_date=None, **kwargs
    ):
        try:
            start_date = fields.Datetime.to_datetime(start_date)
            end_date = fields.Datetime.to_datetime(end_date)
        except ValueError:
            start_date = end_date = None
        vals = super()._prepare_additional_shop_context(
            values, start_date=start_date, end_date=end_date, **kwargs
        )
        vals.update({"start_date": start_date, "end_date": end_date})
        return vals

    def _prepare_product_query_params(self, start_date=None, end_date=None, **kwargs):
        res = super()._prepare_product_query_params(
            start_date=start_date, end_date=end_date, **kwargs
        )
        if start_date is not None or end_date is not None:
            res.update(
                {
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
        return res
