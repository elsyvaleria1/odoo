// @ts-check
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { ActivitiesTile } from "@mail/core/web/activities_tile";
import { InboxTile } from "@mail/core/web/inbox_tile";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import {
    contains,
    mockService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

function stepActions() {
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(
                typeof action === "string"
                    ? action
                    : `${action.tag || action.res_model} ${action.res_id ?? action.context?.active_id ?? ""}`.trim(),
            );
        },
    });
}

test("the activities tile totals the buckets and opens a model's activities", async () => {
    stepActions();
    await mountWithCleanup(ActivitiesTile, {
        props: {
            data: {
                overdue: 2,
                today: 1,
                planned: 4,
                groups: [
                    {
                        model: "res.partner",
                        subkey: "",
                        domain: [],
                        name: "Contact",
                        icon: false,
                        overdue: 2,
                        today: 1,
                        planned: 0,
                    },
                ],
            },
            size: "1x1",
        },
    });
    expect(queryAllTexts(".o_activities_tile_totals strong")).toEqual(["2", "1", "4"]);

    await contains(".o_activities_tile_group").click();
    await contains(".o_activities_tile_totals").click();
    expect.verifySteps(["res.partner", "mail.mail_activity_action_my"]);
});

test("two activity groups of one model are two rows, each opening its own records", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(`${action.res_model} ${JSON.stringify(action.domain)}`);
        },
    });
    const group = {
        model: "mailing.mailing",
        icon: false,
        overdue: 1,
        today: 0,
        planned: 0,
    };
    await mountWithCleanup(ActivitiesTile, {
        props: {
            data: {
                overdue: 2,
                today: 0,
                planned: 0,
                groups: [
                    {
                        ...group,
                        subkey: "",
                        name: "Email Marketing",
                        domain: [["id", "in", [1]]],
                    },
                    {
                        ...group,
                        subkey: "sms",
                        name: "SMS Marketing",
                        domain: [["id", "in", [2]]],
                    },
                ],
            },
            size: "1x1",
        },
    });
    expect(queryAllTexts(".o_activities_tile_group span.text-truncate")).toEqual([
        "Email Marketing",
        "SMS Marketing",
    ]);

    await contains(".o_activities_tile_group:last").click();
    expect.verifySteps(['mailing.mailing [["id","in",[2]]]']);
});

test("the inbox tile counts what is left to read and opens a message's record", async () => {
    stepActions();
    await mountWithCleanup(InboxTile, {
        props: {
            data: {
                count: 3,
                messages: [
                    {
                        id: 9,
                        author: "Mitchell Admin",
                        record_name: "Azure Interior",
                        model: "res.partner",
                        res_id: 7,
                        date: "2026-09-26 09:00:00",
                        preview: "Can we meet?",
                    },
                    {
                        id: 8,
                        author: "OdooBot",
                        record_name: "",
                        model: false,
                        res_id: false,
                        date: "2026-09-25 09:00:00",
                        preview: "Welcome",
                    },
                ],
            },
            size: "2x1",
        },
    });
    expect(".o_inbox_tile_count strong").toHaveText("3");
    expect(queryAllTexts(".o_inbox_tile_message strong")).toEqual([
        "Azure Interior",
        "OdooBot",
    ]);
    expect(".o_inbox_tile_message:first small.text-truncate").toHaveText(
        "Mitchell Admin: Can we meet?",
    );

    await contains(".o_inbox_tile_message:first").click();
    await contains(".o_inbox_tile_message:last").click();
    await contains(".o_inbox_tile_count").click();
    expect.verifySteps([
        "res.partner 7",
        "mail.action_discuss discuss.tab_notification",
        "mail.action_discuss discuss.tab_notification",
    ]);
});

test("an empty inbox says so", async () => {
    await mountWithCleanup(InboxTile, {
        props: { data: { count: 0, messages: [] }, size: "2x1" },
    });
    expect(".o_inbox_tile_count strong").toHaveText("0");
    expect(".o_inbox_tile p").toHaveText("Your inbox is empty.");
});

test("the activities tile opens a group the way the activity systray does", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action, /** @type {any} */ options) {
            expect.step(
                typeof action === "string"
                    ? `${action} ${JSON.stringify(options?.additionalContext?.active_ids)}`
                    : `${action.res_model} ${Object.keys(action.context)
                          .filter((key) => key.startsWith("search_default_activities"))
                          .join(",")}`,
            );
        },
    });
    const group = {
        subkey: "",
        domain: [],
        icon: false,
        planned: 0,
        activity_ids: [],
    };
    await mountWithCleanup(ActivitiesTile, {
        props: {
            data: {
                overdue: 1,
                today: 0,
                planned: 3,
                groups: [
                    {
                        ...group,
                        model: "mail.activity",
                        name: "Other activities",
                        activity_ids: [5, 6],
                        overdue: 1,
                        today: 0,
                    },
                    {
                        ...group,
                        model: "res.partner",
                        name: "Contact",
                        overdue: 0,
                        today: 0,
                        planned: 3,
                    },
                ],
            },
            size: "2x1",
        },
    });
    await contains(".o_activities_tile_group:eq(0)").click();
    await contains(".o_activities_tile_group:eq(1)").click();
    expect.verifySteps([
        "mail.mail_activity_without_access_action [5,6]",
        "res.partner search_default_activities_upcoming_all",
    ]);
});
