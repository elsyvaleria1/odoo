/** @odoo-module native */
import { useProductConfiguratorContext } from "@sale/js/product_configurator_dialog/product_configurator_context";
import { ProductList } from "@sale/js/product_list/product_list";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(ProductList.prototype, {
    setup() {
        super.setup(...arguments);
        this.configuratorContext = useProductConfiguratorContext();

        if (this.configuratorContext.isFrontend) {
            this.optionalProductsTitle = _t("Options");
        }
    },
});
