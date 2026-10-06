/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { formatCurrency } from "@web/core/currency";
import { useEventBus } from "@web/core/utils/hooks";
import comparisonUtils from "@website_sale_comparison/js/website_sale_comparison_utils";

export class ProductRow extends Component {
    static template = "website_sale_comparison.ProductRow";
    static props = {
        id: t.number(),
        display_name: t.string(),
        website_url: t.string(),
        image_url: t.string(),
        price: t.number(),
        strikethrough_price: t.number().optional(),
        prevent_zero_price_sale: t.boolean(),
        currency_id: t.number(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.bus = useEventBus();
    }

    removeProduct() {
        comparisonUtils.removeComparisonProduct(this.props.id, this.bus);
        comparisonUtils.enableDisabledProducts([this.props.id], false);
    }

    /**
     * @return {string}
     */
    get formattedPrice() {
        return formatCurrency(this.props.price, this.props.currency_id);
    }

    /**
     * @return {string}
     */
    get formattedStrikethroughPrice() {
        return formatCurrency(this.props.strikethrough_price, this.props.currency_id);
    }
}
