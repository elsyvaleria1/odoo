/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class IconSelectionField extends Component {
    static template = "event.IconSelectionField";
    static props = { ...standardFieldProps, icons: t.object() };
    props = useProps(this.constructor.props);

    get icon() {
        return this.props.icons[this.props.record.data[this.props.name]];
    }
    get title() {
        return (
            this.props.record.data[this.props.name].charAt(0).toUpperCase() +
            this.props.record.data[this.props.name].slice(1)
        );
    }
}

export const iconSelectionField = {
    component: IconSelectionField,
    displayName: _t("Icon Selection"),
    supportedTypes: ["char", "text", "selection"],
    listViewWidth: ({ hasLabel }) => (!hasLabel ? 20 : false),
    extractProps: ({ options }) => ({
        icons: options,
    }),
};

registry.category("fields").add("event_icon_selection", iconSelectionField);
