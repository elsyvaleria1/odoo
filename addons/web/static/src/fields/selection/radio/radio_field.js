// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { registerField } from "@web/fields/_registry";
import { isFalseEmpty } from "@web/fields/field_utils";
import { SelectionLikeField } from "@web/fields/selection/selection_like_field";
import { standardFieldProps } from "@web/fields/standard_field_props";

let nextId = 0;
/**
 * @typedef {import("@web/fields/standard_field_props").StandardFieldProps & {
 * orientation?: string;
 * label?: string;
 * domain?: any[] | Function;
 * context?: object;
 * }} RadioFieldProps
 */
/** @extends {SelectionLikeField} */
export class RadioField extends SelectionLikeField {
    static template = "web.RadioField";
    static props = {
        ...standardFieldProps,
        orientation: t.string().optional("vertical"),
        label: t.string().optional(),
        domain: t.or([t.array(), t.function()]).optional(),
        context: t.object().optional(),
    };

    setup() {
        super.setup();
        this.id = `radio_field_${nextId++}`;
    }

    /** @returns {Array<[any, string]>} */
    get items() {
        switch (this.type) {
            case "selection":
                return this.field.definition.selection;
            case "many2one":
                return /** @type {any} */ (this.specialData).data;
            default:
                return [];
        }
    }

    /** @param {[any, string]} value */
    onChange(value) {
        if (!this.isReady || this.props.readonly) {
            return;
        }
        switch (this.type) {
            case "selection":
                this.field.update(value[0]);
                break;
            case "many2one":
                this.field.update(value && { id: value[0], display_name: value[1] });
                break;
        }
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
export const radioField = {
    component: RadioField,
    displayName: _t("Radio"),
    supportedOptions: [
        {
            label: _t("Display horizontally"),
            name: "horizontal",
            type: "boolean",
        },
    ],
    supportedTypes: ["many2one", "selection"],
    isEmpty: isFalseEmpty,
    extractProps: ({ options, string }, dynamicInfo) => ({
        orientation: options.horizontal ? "horizontal" : "vertical",
        label: string,
        domain: dynamicInfo.domain,
        context: dynamicInfo.context,
    }),
};

registerField("radio", radioField);
