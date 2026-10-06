/** @odoo-module native */
import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { patch } from "@web/core/utils/patch";

patch(activityGroupOpener, {
    availableViews(context, group) {
        if (group.model !== "account.return") {
            return super.availableViews(...arguments);
        }
        return [[false, "kanban"]];
    },
});
