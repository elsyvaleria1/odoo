import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { describe, expect, test } from "@odoo/hoot";

describe.current.tags("headless");

const ACTIONS = {
    "account.action_view_account_return": {
        views: [
            [11, "kanban"],
            [false, "calendar"],
        ],
        search_view_id: [12, "account.return"],
    },
    "account.action_view_account_audit": {
        views: [[21, "kanban"]],
        search_view_id: [22, "account.audit.search"],
    },
};

function makeContext(done) {
    return {
        services: {
            action: {
                loadAction: async (xmlid) => ACTIONS[xmlid],
                doAction: (action, options) => done.push({ action, options }),
            },
        },
    };
}

test("an account.return activity group opens in kanban only", () => {
    expect(activityGroupOpener.availableViews({}, { model: "account.return" })).toEqual(
        [[false, "kanban"]],
    );
    expect(activityGroupOpener.availableViews({}, { model: "res.partner" })).toEqual([
        [false, "kanban"],
        [false, "list"],
        [false, "form"],
        [false, "activity"],
    ]);
});

test("tax returns and audits open in the kanban and search view of their own action", async () => {
    for (const [subkey, kanbanViewId, searchView] of [
        ["", 11, [12, "account.return"]],
        ["audit", 21, [22, "account.audit.search"]],
    ]) {
        const done = [];
        await activityGroupOpener.open(makeContext(done), {
            model: "account.return",
            name: "Returns",
            subkey,
            domain: [["id", "in", [1]]],
            view_type: "kanban",
        });
        expect(done).toHaveLength(1);
        const { action, options } = done[0];
        expect(action.views).toEqual([[kanbanViewId, "kanban"]]);
        expect(action.search_view_id).toEqual(searchView);
        expect(action.res_model).toBe("account.return");
        expect(action.domain).toEqual([["id", "in", [1]]]);
        expect(action.context.search_default_filter_activities_my).toBe(1);
        expect(options.viewType).toBe("kanban");
    }
});
