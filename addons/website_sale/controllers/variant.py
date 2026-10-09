from odoo.http import Controller, request, route

from odoo.addons.web.controllers.utils import (
    Fragment,
    FragmentResponse,
    render_fragments,
)


class WebsiteSaleVariantController(Controller):
    @route(
        "/website_sale/get_combination_info",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
        website=True,
        readonly=True,
    )
    def get_combination_info_website(
        self,
        product_template_id,
        product_id,
        combination,
        add_qty,
        uom_id=None,
        **kwargs,
    ) -> FragmentResponse:
        product_template_id = product_template_id and int(product_template_id)
        product_id = product_id and int(product_id)
        add_qty = (add_qty and float(add_qty)) or 1.0

        product_template = request.env["product.template"].browse(product_template_id)

        combination_info = product_template._get_combination_info(
            combination=request.env["product.template.attribute.value"].browse(
                combination
            ),
            product_id=product_id,
            add_qty=add_qty,
            uom_id=uom_id,
        )
        combination_info["currency_precision"] = combination_info[
            "currency"
        ].decimal_places

        for key in (
            "product_taxes",
            "taxes",
            "currency",
            "date",
            "combination",
            "discount_start_date",
            "discount_end_date",
        ):
            combination_info.pop(key)

        product = request.env["product.product"].browse(combination_info["product_id"])
        if product and product.id == product_id:
            combination_info["no_product_change"] = True
            return render_fragments(request.env, data=combination_info)

        fragments = []
        if (
            request.website.product_page_image_width != "none"
            and not request.env.context.get("website_sale_no_images", False)
        ):
            product_or_template = product or product_template
            combination_info["display_image"] = bool(product_or_template.image_128)
            # outer: the carousel carries a live Bootstrap instance a morph
            # would leave pointing at replaced indicators
            fragments.append(
                Fragment(
                    "website_sale.shop_product_images",
                    {
                        "product": product_template,
                        "product_variant": product,
                        "website": request.website,
                    },
                    swap="outer",
                )
            )

        if request.website.is_view_active("website_sale.product_tags"):
            all_tags = (
                product.all_product_tag_ids
                if product
                else product_template.product_tag_ids
            )
            fragments.append(
                Fragment(
                    "website_sale.product_tags",
                    {
                        "all_product_tags": all_tags,
                        "_tags_fragment_key": "website_sale.product_tags",
                    },
                )
            )
        return render_fragments(request.env, *fragments, data=combination_info)

    @route(
        "/sale/create_product_variant", type="jsonrpc", auth="public", methods=["POST"]
    )
    def create_product_variant(
        self, product_template_id, product_template_attribute_value_ids, **kwargs
    ):
        return (
            request.env["product.template"]
            .browse(int(product_template_id))
            .create_product_variant(product_template_attribute_value_ids)
        )
