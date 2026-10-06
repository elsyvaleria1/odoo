/** @odoo-module native */
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { products_sort_mapping } from "@website_sale/website_builder/shared";

class ProductsSearchbarOptionPlugin extends Plugin {
    static id = "productsSearchbarOption";

    resources = {
        searchbar_option_order_by_items: products_sort_mapping
            .filter((sort) => sort.query !== "name asc")
            .map((query_and_label) => ({
                label: query_and_label.label,
                orderBy: query_and_label.query,
                dependency: "search_products_opt",
            })),
        searchbar_option_display_items: [
            {
                label: _t("Description"),
                dataAttribute: "displayDescription",
                dependency: "search_products_opt",
            },
            {
                label: _t("Category"),
                dataAttribute: "displayExtraLink",
                dependency: "search_products_opt",
            },
            {
                label: _t("Price"),
                dataAttribute: "displayDetail",
                dependency: "search_products_opt",
            },
            {
                label: _t("Image"),
                dataAttribute: "displayImage",
                dependency: "search_products_opt",
            },
        ],
    };
}

registry
    .category("website-plugins")
    .add(ProductsSearchbarOptionPlugin.id, ProductsSearchbarOptionPlugin);
