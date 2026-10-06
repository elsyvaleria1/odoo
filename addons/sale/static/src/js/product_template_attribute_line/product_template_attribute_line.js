/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useProductConfiguratorContext } from "@sale/js/product_configurator_dialog/product_configurator_context";
import { formatCurrency } from "@web/core/currency";
import { _t } from "@web/core/translation";

import { BadgeExtraPrice } from "../badge_extra_price/badge_extra_price.js";
import { getSelectedCustomPtav } from "../sale_utils.js";

export class ProductTemplateAttributeLine extends Component {
    static components = { BadgeExtraPrice };
    static template = "sale.ProductTemplateAttributeLine";
    static props = {
        productTmplId: t.number(),
        id: t.number(),
        attribute: t.object({
            id: t.number(),
            name: t.string(),
            display_type: t.customValidator(t.string(), (type) =>
                ["color", "multi", "pills", "radio", "select", "image"].includes(type),
            ),
        }),
        attribute_values: t.array(
            t.object({
                id: t.number(),
                name: t.string(),
                html_color: t.or([t.boolean(), t.string()]),
                image: t.or([t.boolean(), t.string()]),
                is_custom: t.boolean(),
                price_extra: t.number(),
                excluded: t.boolean().optional(),
            }),
        ),
        selected_attribute_value_ids: t.array(t.number()),
        create_variant: t.customValidator(t.string(), (type) =>
            ["always", "dynamic", "no_variant"].includes(type),
        ),
        customValue: t.or([t.literal(false), t.string()]).optional(),
        show_extra_price: t.boolean(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.configuratorContext = useProductConfiguratorContext();
    }

    /** @param {Event} event */
    updateSelectedPTAV(event) {
        this.configuratorContext.updateProductTemplateSelectedPTAV(
            this.props.productTmplId,
            this.props.id,
            event.target.value,
            this.props.attribute.display_type === "multi",
        );
    }

    /** @param {Event} event */
    updateCustomValue(event) {
        this.configuratorContext.updatePTAVCustomValue(
            this.props.productTmplId,
            this.props.selected_attribute_value_ids[0],
            event.target.value,
        );
    }

    /** @return {String} */
    getPTAVTemplate() {
        switch (this.props.attribute.display_type) {
            case "select":
                return "sale.ptav_select";
            case "radio":
                return "sale.ptav_radio";
            case "pills":
                return "sale.ptav_pills";
            case "color":
                return "sale.ptav_color";
            case "multi":
                return "sale.ptav_multi";
            case "image":
                return "sale.ptav_image";
        }
    }

    /**
     * @param {Object} ptav
     * @return {String}
     */
    getPTAVSelectName(ptav) {
        if (ptav.price_extra) {
            const sign = ptav.price_extra > 0 ? "+" : "-";
            const price = formatCurrency(
                Math.abs(ptav.price_extra),
                this.configuratorContext.currency.id,
            );
            return ptav.name + " (" + sign + " " + price + ")";
        } else {
            return ptav.name;
        }
    }

    /** @return {Boolean} */
    isSelectedPTAVCustom() {
        return !!getSelectedCustomPtav(this.props);
    }

    get showValuesChoice() {
        return (
            (this.configuratorContext.canChangeVariant ||
                this.props.create_variant === "no_variant") &&
            (this.props.attribute_values.length > 1 ||
                this.props.attribute.display_type === "multi")
        );
    }

    get customValuePlaceholder() {
        return _t("Enter a customized value");
    }

    /** @return {Boolean} */
    hasPTAVCustom() {
        return this.props.attribute_values.some((ptav) => ptav.is_custom);
    }
}
