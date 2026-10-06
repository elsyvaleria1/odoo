// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { registerField } from "@web/fields/_registry";
import { FieldComponent } from "@web/fields/field_component";
import { standardFieldProps } from "@web/fields/standard_field_props";

const log = makeLogger("web.field.boolean_icon");

export class BooleanIconField extends FieldComponent {
    static template = "web.BooleanIconField";
    static props = {
        ...standardFieldProps,
        icon: t.string().optional("fa-regular fa-square-check"),
        label: t.string().optional(),
        autosave: t.boolean().optional(),
    };

    update() {
        if (this.props.readonly) {
            return;
        }
        const inEdition = this.props.record.isInEdition;
        const save = this.props.autosave ?? !inEdition;
        log.logic("update", () => ({
            name: this.props.name,
            inEdition,
            autosave: this.props.autosave,
            save,
        }));
        return this.field.update(!this.field.value, { save });
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
export const booleanIconField = {
    component: BooleanIconField,
    displayName: _t("Boolean Icon"),
    interactiveOutsideEdition: true,
    supportedOptions: [
        {
            label: _t("Icon"),
            name: "icon",
            type: "string",
        },
        {
            label: _t("Autosave"),
            name: "autosave",
            type: "boolean",
            help: _t(
                "If checked, the record is saved as soon as the icon is toggled. By default it is saved only when toggled outside edition, where nothing else would save it.",
            ),
        },
    ],
    supportedTypes: ["boolean"],
    extractProps: ({ options, string }, dynamicInfo) => ({
        icon: options.icon,
        label: string,
        autosave: "autosave" in options ? exprToBoolean(options.autosave) : undefined,
    }),
};

registerField("boolean_icon", booleanIconField);
