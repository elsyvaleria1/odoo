/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { usePosSelfOrderContext } from "@pos_self_order/app/pos_self_order_context";
import { useSelfOrder } from "@pos_self_order/app/services/self_order_service";

import { AttributeSelectionHelper } from "./attribute_selection_helper.js";

export class AttributeSelection extends Component {
    static template = "pos_self_order.AttributeSelection";
    static props = {
        productTemplate: t.any(),
        onSelection: t.any().optional(),
        isCombo: t.any().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.selfOrderContext = usePosSelfOrderContext();
        this.selfOrder = useSelfOrder();
        this.envSelectedValues = proxy(this.selfOrderContext.selectedValues);
    }

    get selectedValues() {
        return (this.envSelectedValues[this.props.productTemplate.id] ??=
            new AttributeSelectionHelper(this.selfOrder));
    }

    isValueSelected(attribute, value) {
        return this.selectedValues.isValueSelected(attribute, value);
    }

    selectAttribute(attribute, value) {
        this.selectedValues.selectAttribute(attribute, value, this.props.onSelection);
    }

    availableAttributeValue(attribute) {
        const isKiosk = this.selfOrder.kioskMode;
        const isNoVariantCreation =
            attribute.attribute_id.create_variant === "no_variant";
        return attribute.product_template_value_ids.filter((a) => {
            if (isKiosk && a.is_custom) {
                return false;
            }
            if (this.props.isCombo) {
                return isNoVariantCreation;
            }
            return true;
        });
    }

    getCustomSelectedValue(attribute) {
        if (attribute.attribute_id.display_type === "multi") {
            return null;
        }
        const valueId = this.selectedValues.getSelectedValue(attribute);
        if (!valueId) {
            return null;
        }

        const value =
            this.selfOrder.models["product.template.attribute.value"].get(valueId);
        if (value?.is_custom) {
            return value;
        }

        return null;
    }

    shouldShowPriceExtra(value) {
        const priceExtra = value.price_extra;
        return !this.selfOrder.config.currency_id.isZero(priceExtra);
    }

    formatExtraPrice(value) {
        const priceExtra = value.price_extra;
        const sign = priceExtra < 0 ? "- " : "+ ";
        return sign + this.selfOrder.formatMonetary(Math.abs(priceExtra));
    }
}
