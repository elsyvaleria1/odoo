/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

export class ProductHeaderShopOption extends BaseOptionComponent {
    static template = "website_sale.ProductHeaderShopOption";
    static selector = "#products_grid:has(header.o_wsale_products_header_is_shop)";
    static editableOnly = false;
    static reloadTarget = true;
    static title = _t("Shop Header");
}

class ProductHeaderShopOptionPlugin extends Plugin {
    static id = "ProductHeaderShopOptionPlugin";

    resources = {
        builder_options: ProductHeaderShopOption,
    };
}

registry
    .category("website-plugins")
    .add(ProductHeaderShopOptionPlugin.id, ProductHeaderShopOptionPlugin);
