// @ts-check
/** @odoo-module native */

import { Component, proxy, useProps } from "@odoo/owl";
import { colorScheme, useColorScheme } from "@web/core/color_scheme";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class AppearanceControls extends Component {
    static template = "web.AppearanceControls";
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.colorSchemeService = /** @type {any} */ (useService("color_scheme"));
        this.densityService = /** @type {any} */ (useService("density"));
        this.density = proxy(this.densityService.state);
        this.scheme = useColorScheme();
        this.state = proxy({ scheme: this.storedScheme });
    }

    get storedScheme() {
        const stored = user.settings?.color_scheme;
        return stored === "light" || stored === "dark" ? stored : "system";
    }

    get schemes() {
        return [
            { value: "system", label: _t("Automatic"), icon: "fa-circle-half-stroke" },
            { value: "light", label: _t("Light"), icon: "fa-sun" },
            { value: "dark", label: _t("Dark"), icon: "fa-moon" },
        ];
    }

    get densities() {
        return [
            { value: "default", label: _t("Default") },
            { value: "compact", label: _t("Compact") },
            { value: "condensed", label: _t("Condensed") },
        ];
    }

    /** @param {"system" | "light" | "dark"} value */
    async setScheme(value) {
        this.state.scheme = value;
        await user.setUserSettings("color_scheme", value);
        colorScheme.publish(
            value === "system" ? this.colorSchemeService.systemColorScheme : value,
        );
    }

    /** @param {string} value */
    setDensity(value) {
        return this.densityService.set(value);
    }
}

registry.category("user_menuitems").add("appearance", () => ({
    type: "component",
    contentComponent: AppearanceControls,
    sequence: 10,
}));
registry.category("user_menuitems").add("appearance_separator", () => ({
    type: "separator",
    sequence: 15,
}));
