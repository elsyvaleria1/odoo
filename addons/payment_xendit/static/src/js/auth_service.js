/** @odoo-module native */
import { EventBus } from "@odoo/owl";
import { registry } from "@web/core/registry";

import { AuthUI } from "./auth_ui.js";

const bus = new EventBus();

const AUTH_UI_ENTRY = { Component: AuthUI, props: { bus } };

export const authService = {
    start() {
        registry.category("main_components").add("AuthUI", AUTH_UI_ENTRY);
    },
};
registry.category("services").add("auth_ui", authService);
