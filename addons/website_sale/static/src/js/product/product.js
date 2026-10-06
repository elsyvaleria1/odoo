/** @odoo-module native */
import { t } from "@odoo/owl";
import { Product, productProps } from "@sale/js/product/product";
import { useProductConfiguratorContext } from "@sale/js/product_configurator_dialog/product_configurator_context";
import { formatCurrency } from "@web/core/currency";
import { patch } from "@web/core/utils/patch";

Object.assign(productProps, {
    strikethrough_price: t.number().optional(),
    can_be_sold: t.boolean().optional(),
    category_name: t.string().optional(),
    currency_name: t.string().optional(),
});

patch(Product.prototype, {
    setup() {
        super.setup(...arguments);
        this.configuratorContext = useProductConfiguratorContext();
    },

    /**
     * @return {String}
     */
    get formattedStrikethroughPrice() {
        return formatCurrency(
            this.props.strikethrough_price,
            this.configuratorContext.currency.id,
        );
    },
});
