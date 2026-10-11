/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import {
    ReferenceField,
    referenceField,
} from "@web/fields/relational/reference/reference_field";

export class EventMailTemplateReferenceField extends ReferenceField {
    static template = "event.mailTemplateReferenceField";

    setup() {
        const returnVal = super.setup();
        const defaultSelect = this.selection?.[0][0];
        if (defaultSelect) {
            this.state.currentRelation = defaultSelect;
        }
        return returnVal;
    }

    get m2oProps() {
        const props = super.m2oProps;
        if (props.readonly) {
            props.canOpen = false;
        }
        return props;
    }
}

export const eventMailTemplateReferenceField = {
    ...referenceField,
    component: EventMailTemplateReferenceField,
    displayName: _t("Event Mail Template Reference"),
};

registry
    .category("fields")
    .add("EventMailTemplateReferenceField", eventMailTemplateReferenceField);
