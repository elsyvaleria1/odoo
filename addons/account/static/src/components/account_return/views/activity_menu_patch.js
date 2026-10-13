/** @odoo-module native */
import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { patch } from "@web/core/utils/patch";

const ACTION_BY_SUBKEY = {
    audit: "account.action_view_account_audit",
};
const TAX_RETURN_ACTION = "account.action_view_account_return";

patch(activityGroupOpener, {
    availableViews(context, group) {
        if (group.model !== "account.return") {
            return super.availableViews(...arguments);
        }
        return [[false, "kanban"]];
    },

    async execute(context, group, domain, views, actionContext, newWindow) {
        if (group.model !== "account.return") {
            return super.execute(...arguments);
        }
        const { action } = context.services;
        const loaded = await action.loadAction(
            ACTION_BY_SUBKEY[group.subkey] || TAX_RETURN_ACTION,
        );
        const viewIds = Object.fromEntries(
            loaded.views.map(([viewId, viewType]) => [viewType, viewId]),
        );
        return action.doAction(
            {
                context: actionContext,
                domain,
                name: group.name,
                res_model: group.model,
                search_view_id: loaded.search_view_id,
                type: "ir.actions.act_window",
                views: views.map(([viewId, viewType]) => [
                    viewIds[viewType] || viewId,
                    viewType,
                ]),
            },
            { newWindow, clearBreadcrumbs: true, viewType: group.view_type },
        );
    },
});
