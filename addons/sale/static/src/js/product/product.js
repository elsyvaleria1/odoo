/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useProductConfiguratorContext } from "@sale/js/product_configurator_dialog/product_configurator_context";
import { formatCurrency } from "@web/core/currency";
import { _t } from "@web/core/translation";

import { ProductTemplateAttributeLine as PTAL } from "../product_template_attribute_line/product_template_attribute_line.js";
import { QuantityButtons } from "../quantity_buttons/quantity_buttons.js";
import { getSelectedCustomPtav } from "../sale_utils.js";

export const productProps = {
    id: t.or([t.number(), t.literal(false)]).optional(),
    product_tmpl_id: t.number(),
    display_name: t.string(),
    description_sale: t.or([t.boolean(), t.string()]),
    price: t.number(),
    quantity: t.number(),
    uom: t.object().optional(),
    available_uoms: t.array(t.object()).optional(),
    attribute_lines: t.array(),
    optional: t.boolean(),
    imageURL: t.string().optional(),
    archived_combinations: t.array(),
    exclusions: t.object(),
    parent_exclusions: t.object(),
    parent_product_tmpl_id: t.number().optional(),
    price_info: t.string().optional(),
    selectedComboItems: t.array(t.object({ name: t.string() })).optional(),
    show_extra_price: t.boolean().optional(true),
};

export class Product extends Component {
    static components = { PTAL, QuantityButtons };
    static template = "sale.Product";
    static props = productProps;
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.configuratorContext = useProductConfiguratorContext();
    }

    /** @return {String} */
    getFormattedPrice() {
        return formatCurrency(this.props.price, this.configuratorContext.currency.id);
    }

    /** @return {Boolean} */
    get isMainProduct() {
        return (
            this.configuratorContext.mainProductTmplId === this.props.product_tmpl_id
        );
    }

    /** @return {String} */
    get imageUrl() {
        const modelPath = this.props.id
            ? `product.product/${this.props.id}`
            : `product.template/${this.props.product_tmpl_id}`;
        return `/web/image/${modelPath}/image_256`;
    }

    /** @return {Boolean} */
    shouldShowPtal(ptal) {
        return (
            this.configuratorContext.canChangeVariant ||
            ptal.create_variant === "no_variant" ||
            !!getSelectedCustomPtav(ptal)
        );
    }

    get UoMTitle() {
        return _t("Packaging");
    }

    selectUoM(event) {
        return this.configuratorContext.setUoM(
            this.props.product_tmpl_id,
            parseInt(event.target.value),
        );
    }
}
