// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { SelectMenu } from "@web/components/select_menu/select_menu";
import { inputModality } from "@web/core/input_modality";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { registerField } from "@web/fields/_registry";
import { placeholderFieldOption } from "@web/fields/field_options";
import { isFalseEmpty } from "@web/fields/field_utils";
import { SelectionLikeField } from "@web/fields/selection/selection_like_field";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class SelectionField extends SelectionLikeField {
    static components = {
        SelectMenu,
    };
    static template = "web.SelectionField";
    static props = {
        ...standardFieldProps,
        placeholder: t.string().optional(),
        required: t.boolean().optional(),
        domain: t.or([t.array(), t.function()]).optional(),
        context: t.object().optional(),
        autosave: t.boolean().optional(false),
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    get choices() {
        return this.options.map(([value, label]) => ({ value, label }));
    }
    get isBottomSheet() {
        return this.ui.isSmall && inputModality.isTouch;
    }
    onChange(value) {
        if (!this.isReady || this.props.readonly) {
            return;
        }
        const options = { save: this.props.autosave };
        switch (this.type) {
            case "many2one": {
                const next = this.many2oneValueFor(value, this.options);
                if (next !== undefined) {
                    this.field.update(next, options);
                }
                break;
            }
            case "selection":
                this.field.update(value ?? false, options);
                break;
        }
    }
}

export const selectionField = {
    component: SelectionField,
    displayName: _t("Selection"),
    supportedOptions: [placeholderFieldOption()],
    supportedTypes: ["many2one", "selection"],
    isEmpty: isFalseEmpty,
    interactiveOutsideEdition: ({ viewType }) => viewType === "kanban",
    extractProps({ viewType, placeholder = undefined }, dynamicInfo) {
        return {
            autosave: viewType === "kanban",
            placeholder,
            required: dynamicInfo.required,
            domain: dynamicInfo.domain,
            context: dynamicInfo.context,
        };
    },
};

registerField("selection", /** @type {any} */ (selectionField));
