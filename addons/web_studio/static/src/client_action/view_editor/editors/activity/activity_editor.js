/** @odoo-module native */
import { activityView } from "@mail/views/web/activity/activity_view";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

// No Sidebar: the view editor falls back to the plain view, which is how
// activity has always been edited. The entry is what lists the type in the
// action editor and the editor menu, and what makes "editable in Studio" a
// fact about this registry alone.
registry.category("studio_editors").add("activity", {
    ...activityView,
    label: _t("Activity"),
    icon: "fa-regular fa-clock",
    group: "general",
});
