// @ts-check
/** @odoo-module native */

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
export class ColorPickerSolidTab extends Component {
    static template = "web.ColorPickerSolidTab";
    static props = null;
    props = useProps(this.constructor.props);
}

registry.category("color_picker_tabs").add(
    "web.solid",
    {
        id: "solid",
        name: _t("Solid"),
        component: ColorPickerSolidTab,
    },
    { sequence: 40 },
);
