/** @odoo-module native */
import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { Domain } from "@web/core/domain";
import { patch } from "@web/core/utils/patch";

patch(activityGroupOpener, {
    open(context, group, filter = "all", newWindow = false) {
        if (group.model !== "crm.lead") {
            return super.open(...arguments);
        }
        const actionContext = { force_search_count: 1 };
        if (filter === "my" || filter === "all") {
            actionContext.search_default_activities_overdue = 1;
            actionContext.search_default_activities_today = 1;
        } else if (filter === "overdue") {
            actionContext.search_default_activities_overdue = 1;
        } else if (filter === "today") {
            actionContext.search_default_activities_today = 1;
        } else {
            actionContext.search_default_activities_upcoming_all = 1;
        }
        const { action } = context.services;
        return action.loadAction("crm.crm_lead_action_my_activities").then((loaded) => {
            loaded.domain = Domain.and([
                loaded.domain || [],
                [["active", "in", [true, false]]],
            ]).toList();
            return action.doAction(loaded, {
                newWindow,
                additionalContext: actionContext,
                clearBreadcrumbs: true,
            });
        });
    },
});
