// @ts-check
/** @odoo-module native */

import { Component, useProps } from "@odoo/owl";
import { CustomColorPicker } from "@web/components/color_picker/custom_color_picker/custom_color_picker";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { isColorGradient } from "@web/core/utils/format/colors";
export class ColorPickerCustomTab extends Component {
    static template = "web.ColorPickerCustomTab";
    static components = { CustomColorPicker };
    static props = null;
    props = useProps(this.constructor.props);

    /**
     * @param {string} color
     * @returns {boolean}
     */
    isValidCustomColor(color) {
        return Boolean(color) && color.slice(7, 9) !== "00" && !isColorGradient(color);
    }
}

registry.category("color_picker_tabs").add("web.custom", {
    id: "custom",
    name: _t("Custom"),
    component: ColorPickerCustomTab,
});
