// @ts-check
import { defineCalendarModels } from "@calendar/../tests/calendar_test_helpers";
import { AgendaTile } from "@calendar/home_tile/agenda_tile";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import {
    contains,
    mockService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineCalendarModels();

const EVENTS = [
    {
        id: 1,
        name: "Company offsite",
        start: "2026-09-26 00:00:00",
        stop: "2026-09-26 23:59:59",
        allday: true,
        location: "",
    },
    {
        id: 2,
        name: "Standup",
        start: "2026-09-26 10:00:00",
        stop: "2026-09-26 10:15:00",
        allday: false,
        location: "Room 2",
    },
    {
        id: 3,
        name: "Review",
        start: "2026-09-26 15:00:00",
        stop: "2026-09-26 16:00:00",
        allday: false,
        location: "",
    },
    {
        id: 4,
        name: "Wrap-up",
        start: "2026-09-26 17:00:00",
        stop: "2026-09-26 17:30:00",
        allday: false,
        location: "",
    },
];

test("the agenda shows today's events for its size and opens one", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action) {
            expect.step(
                typeof action === "string"
                    ? action
                    : `${action.res_model} ${action.res_id}`,
            );
        },
    });
    await mountWithCleanup(AgendaTile, {
        props: { data: { events: EVENTS, more: false }, size: "1x1" },
    });
    expect(
        queryAllTexts(".o_agenda_tile_event span.text-truncate > span:first-child"),
    ).toEqual(["Company offsite", "Standup", "Review"]);
    expect(".o_agenda_tile_event:first .o_agenda_tile_time").toHaveText("All day");
    expect(".o_agenda_tile_event:eq(1) small").toHaveText("Room 2");

    await contains(".o_agenda_tile_event:eq(1)").click();
    await contains(".o_agenda_tile_more").click();
    expect.verifySteps(["calendar.event 2", "calendar.action_calendar_event"]);
});

test("a free day says so", async () => {
    await mountWithCleanup(AgendaTile, {
        props: { data: { events: [], more: false }, size: "2x1" },
    });
    expect(".o_agenda_tile p").toHaveText("Nothing else is planned for today.");
    expect(".o_agenda_tile_more").toHaveCount(0);
});
