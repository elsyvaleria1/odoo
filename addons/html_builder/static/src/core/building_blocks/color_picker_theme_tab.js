/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

export class ColorPickerThemeTab extends Component {
    static template = "html_builder.ColorPickerThemeTab";
    static props = null;
    props = useProps(this.constructor.props);
}

registry.category("color_picker_tabs").add(
    "html_builder.theme",
    {
        id: "theme",
        name: _t("Theme"),
        component: ColorPickerThemeTab,
    },
    { sequence: 10 },
);
