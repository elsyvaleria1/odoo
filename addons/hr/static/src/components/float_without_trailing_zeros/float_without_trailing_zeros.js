/** @odoo-module native */
import { localization } from "@web/core/l10n/localization";
import { registry } from "@web/core/registry";
import { FloatField, floatField } from "@web/fields/basic/float/float_field";

const fieldRegistry = registry.category("fields");

class FloatWithoutTrailingZeros extends FloatField {
    get formattedValue() {
        const decimalPoint = RegExp.escape(localization.decimalPoint);
        return super.formattedValue
            .replace(new RegExp(`(${decimalPoint}\\d*?[1-9])0+$`), "$1")
            .replace(new RegExp(`${decimalPoint}0+$`), "");
    }
}

const floatWithoutTrailingZeros = {
    ...floatField,
    component: FloatWithoutTrailingZeros,
};

fieldRegistry.add("float_without_trailing_zeros", floatWithoutTrailingZeros);
