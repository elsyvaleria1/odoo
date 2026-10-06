/** @odoo-module native */
import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { patch } from "@web/core/utils/patch";

patch(activityGroupOpener, {
    open(context, group, filter, newWindow) {
        if (group.model === "calendar.event") {
            return context.services.action.doAction("calendar.action_calendar_event", {
                newWindow,
                additionalContext: {
                    default_mode: "day",
                    search_default_mymeetings: 1,
                },
                clearBreadcrumbs: true,
            });
        }
        return super.open(...arguments);
    },
});
