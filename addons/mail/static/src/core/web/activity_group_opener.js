// @ts-check
/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { Domain } from "@web/core/domain";

const log = makeLogger("mail.activity");

/**
 * @typedef {{
 *  id?: number,
 *  model: string,
 *  name: string,
 *  activity_ids?: number[],
 *  domain?: any,
 *  view_type?: string,
 *  is_todo?: boolean,
 * }} ActivityGroup
 * @typedef {"all" | "my" | "overdue" | "today" | "upcoming_all"} ActivityFilter
 * @typedef {import("@web/core/app_context").AppContext} AppContext
 */

/** @type {Record<ActivityFilter, Record<string, number>>} */
const FILTERS = {
    all: { search_default_activities_overdue: 1, search_default_activities_today: 1 },
    my: { search_default_activities_overdue: 1, search_default_activities_today: 1 },
    overdue: { search_default_activities_overdue: 1 },
    today: { search_default_activities_today: 1 },
    upcoming_all: { search_default_activities_upcoming_all: 1 },
};

export const activityGroupOpener = {
    /**
     * @param {AppContext} context
     * @param {ActivityGroup} group
     * @returns {Array<[number | false, string]>}
     */
    availableViews(context, group) {
        return [
            [false, "kanban"],
            [false, "list"],
            [false, "form"],
            [false, "activity"],
        ];
    },

    /**
     * @param {AppContext} context
     * @param {ActivityGroup} group
     * @param {ActivityFilter} [filter]
     * @param {boolean} [newWindow]
     */
    open(context, group, filter = "all", newWindow = false) {
        log.logic("openActivityGroup", () => ({
            model: group.model,
            filter,
            newWindow,
            activities: group.activity_ids?.length,
        }));
        if (group.model === "mail.activity") {
            return context.services.action.doAction(
                "mail.mail_activity_without_access_action",
                {
                    newWindow,
                    additionalContext: {
                        active_ids: group.activity_ids,
                        active_model: "mail.activity",
                    },
                },
            );
        }
        const domain = group.domain ? Domain.and([[], group.domain]).toList() : [];
        return this.execute(
            context,
            group,
            domain,
            this.availableViews(context, group),
            {
                force_search_count: 1,
                search_default_filter_activities_my: 1,
                ...FILTERS[filter],
            },
            newWindow,
        );
    },

    /**
     * @param {AppContext} context
     * @param {ActivityGroup} group
     * @param {any[]} domain
     * @param {Array<[number | false, string]>} views
     * @param {Record<string, any>} actionContext
     * @param {boolean} [newWindow]
     */
    execute(context, group, domain, views, actionContext, newWindow) {
        return context.services.action.doAction(
            {
                context: actionContext,
                domain,
                name: group.name,
                res_model: group.model,
                search_view_id: [false],
                type: "ir.actions.act_window",
                views,
            },
            { newWindow, clearBreadcrumbs: true, viewType: group.view_type },
        );
    },
};
