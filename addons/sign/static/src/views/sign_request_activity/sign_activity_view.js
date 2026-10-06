/** @odoo-module native */
import { activityView } from "@mail/views/web/activity/activity_view";
import { registry } from "@web/core/registry";

import { SignActivityController } from "./sign_activity_controller.js";

export const SignActivityView = {
    ...activityView,
    Controller: SignActivityController,
};

registry.category("views").add("sign_activity", SignActivityView);
