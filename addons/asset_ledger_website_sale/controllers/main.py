from odoo import http
from odoo.fields import Domain
from odoo.http import request


class WebsiteSaleVehicleCatalog(http.Controller):
    @http.route("/vehiculos", type="http", auth="public", website=True, sitemap=True)
    def vehicles_catalog(self, **kwargs):
        website = request.website
        category = request.env.ref(
            "asset_ledger_website_sale.product_public_category_vehicles",
            raise_if_not_found=False,
        )
        domain = Domain("is_published", "=", True) & website.website_domain()
        if category:
            domain &= Domain("public_categ_ids", "child_of", category.id)

        products = (
            request.env["product.template"]
            .sudo()
            .search(domain, order="website_sequence, name")
        )
        tags = products.product_tag_ids.filtered("visible_to_customers").sorted(
            "sequence"
        )
        return request.render(
            "asset_ledger_website_sale.vehicles_catalog_page",
            {"products": products, "vehicle_tags": tags},
        )
