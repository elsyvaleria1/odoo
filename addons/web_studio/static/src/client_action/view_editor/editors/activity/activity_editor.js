/** @odoo-module native */
import { activityView } from "@mail/views/web/activity/activity_view";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

registry.category("studio_editors").add("activity", {
    ...activityView,
    label: _t("Activity"),
    icon: "fa-regular fa-clock",
    group: "general",
});
