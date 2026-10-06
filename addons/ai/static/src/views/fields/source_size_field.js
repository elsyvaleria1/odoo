/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { formatFloat } from "@web/core/utils/format/numbers";
import { IntegerField } from "@web/fields/basic/integer/integer_field";

export class SourceSizeIntegerField extends IntegerField {
    get formattedValue() {
        if (!this.value) {
            return "";
        }
        return `${formatFloat(this.value, { humanReadable: true })}B`;
    }
}

const sourceSizeIntegerField = {
    component: SourceSizeIntegerField,
    displayName: _t("SourceSizeIntegerField"),
    supportedTypes: ["integer"],
};

registry.category("fields").add("source_size", sourceSizeIntegerField);
