/** @odoo-module native */

import { DomainSelector } from "@web/components/domain_selector";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(DomainSelector.prototype, {
    /**
     * @param {Object} fieldDef
     * @param {string} fieldDef.type
     * @returns {Object}
     */
    getOperatorEditorInfo(fieldDef) {
        const info = super.getOperatorEditorInfo(fieldDef);

        const originalExtractProps = info.extractProps;
        info.extractProps = (args) => {
            const props = originalExtractProps.call(info, args);
            const [operator] = args.value;

            if (operator === "geo_in_active") {
                if (!props.options.some(([op]) => op === "geo_in_active")) {
                    props.options.push(["geo_in_active", _t("in active records")]);
                }
                props.value = "geo_in_active";
            }

            if (operator === "geo_not_in_active") {
                if (!props.options.some(([op]) => op === "geo_not_in_active")) {
                    props.options.push([
                        "geo_not_in_active",
                        _t("not in active records"),
                    ]);
                }
                props.value = "geo_not_in_active";
            }

            return props;
        };

        return info;
    },
});
