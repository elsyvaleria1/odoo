import { defineAppointmentMockServer } from "@calendar/../tests/booking/appointment_mock_server";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { beforeEach, expect, test } from "@odoo/hoot";
import { animationFrame, mockDate } from "@odoo/hoot-mock";
import {
    changeScale,
    toggleSectionFilter,
} from "@web/../tests/views/calendar/calendar_test_helpers";
import {
    contains,
    defineActions,
    defineModels,
    fields,
    getService,
    models,
    mountView,
    mountWebClient,
    onRpc,
    serverState,
    switchView,
} from "@web/../tests/web_test_helpers";

class CalendarEvent extends models.Model {
    _name = "calendar.event";
    _records = [
        {
            id: 5,
            user_id: serverState.userId,
            partner_id: 4,
            name: "event 1",
            start: "2016-12-13 15:55:05",
            stop: "2016-12-15 18:55:05",
            allday: false,
            partner_ids: [4],
        },
        {
            id: 6,
            user_id: serverState.userId,
            partner_id: 5,
            name: "event 2",
            start: "2016-12-18 08:00:00",
            stop: "2016-12-18 09:00:00",
            allday: false,
            partner_ids: [4],
        },
    ];
    _views = {
        calendar: `
            <calendar js_class="attendee_calendar" date_start="start" date_stop="stop">
                <field name="name"/>
                <field name="partner_ids" write_model="calendar.filter" write_field="partner_id"/>
            </calendar>
        `,
        list: `<list sample="1"/>`,
    };

    user_id = fields.Many2one({ relation: "users" });
    partner_id = fields.Many2one({ relation: "partner" });
    name = fields.Char();
    start = fields.Datetime();
    stop = fields.Datetime();
    allday = fields.Boolean();
    partner_ids = fields.One2many({ relation: "partner" });
}

class CalendarFilter extends models.Model {
    _records = [
        { id: 3, user_id: serverState.userId, partner_id: 4, partner_checked: true },
    ];

    user_id = fields.Many2one({ relation: "users" });
    partner_id = fields.Many2one({ relation: "partner" });
    partner_checked = fields.Boolean();
}

class Partner extends models.Model {
    _records = [
        { id: 4, name: "Partner 4", image_1920: "DDD" },
        { id: 5, name: "Partner 5", image_1920: "DDD" },
    ];

    name = fields.Char();
    image_1920 = fields.Binary();
}

class Users extends models.Model {
    _records = [{ id: serverState.userId, name: "User 4", partner_id: 4 }];

    name = fields.Char();
    partner_id = fields.Many2one({ relation: "partner" });
    image_1920 = fields.Binary();
}

defineModels([CalendarEvent, CalendarFilter, Partner, Users]);
defineMailModels();
defineAppointmentMockServer();

const GOOGLE = { code: "google", label: "Google", key: "calendar_google" };
const OUTLOOK = { code: "microsoft", label: "Outlook", key: "calendar_microsoft" };

onRpc("calendar_sync_providers", () => [GOOGLE]);
onRpc("/calendar/check_credentials", async () => ({ calendar_google: true }));
onRpc("/calendar_sync/google/sync_data", () => ({ status: "no_new_event" }));
onRpc("check_synchronization_status", async () => ({ calendar_google: "sync_active" }));
onRpc("get_attendee_detail", () => []);
onRpc("get_default_duration", () => 3.25);

beforeEach(() => {
    mockDate("2016-12-12 08:00:00");
});

test.tags("desktop");
test(`each provider is synchronized as the view loads`, async () => {
    onRpc("/calendar_sync/google/sync_data", async function () {
        expect.step("sync_data");
        this.env["calendar.event"].create({
            user_id: serverState.userId,
            partner_id: 4,
            name: "event from google",
            start: "2016-12-28 15:55:05",
            stop: "2016-12-29 18:55:05",
            allday: false,
            partner_ids: [4],
        });
        return { status: "need_refresh" };
    });
    onRpc("calendar.event", "search_read", ({ method }) => {
        expect.step(method);
    });

    await mountView({
        type: "calendar",
        resModel: "calendar.event",
        arch: `
            <calendar js_class="attendee_calendar" date_start="start" date_stop="stop" attendee="partner_ids" mode="month">
                <field name="name"/>
                <field name="partner_ids" write_model="calendar.filter" write_field="partner_id"/>
            </calendar>
        `,
    });
    expect.verifySteps(["sync_data", "search_read"]);

    // select the partner filter
    await toggleSectionFilter("partner_ids");
    // sync_data was called a first time without filter, event from google calendar was created twice
    expect(`.fc-event`).toHaveCount(4, {
        message: "should display 4 events on the month",
    });
    expect.verifySteps(["sync_data", "search_read"]);

    await contains(`.o_datetime_picker_header .o_next`).click();
    await contains(`.o_datetime_picker .o_date_item_cell`).click();
    expect.verifySteps(["sync_data", "search_read"]);

    await changeScale("month");
    expect.verifySteps(["sync_data", "search_read"]);

    await contains(`.o_calendar_button_today`).click();
    expect.verifySteps(["sync_data", "search_read"]);
    expect(`.fc-event`).toHaveCount(7, {
        message: "should now display 7 events on the month",
    });
});

test(`a view destroyed during a synchronization does not reload`, async () => {
    defineActions([
        {
            id: 1,
            name: "Partners",
            res_model: "calendar.event",
            type: "ir.actions.act_window",
            views: [
                [false, "list"],
                [false, "calendar"],
            ],
        },
    ]);

    const deferred = Promise.withResolvers();
    onRpc("/calendar_sync/google/sync_data", async function () {
        expect.step("sync_data");
        return deferred.promise;
    });
    onRpc("calendar.event", "search_read", ({ method }) => {
        expect.step(method);
    });

    await mountWebClient();
    await getService("action").doAction(1);
    expect.verifySteps([]);

    await switchView("calendar");
    expect.verifySteps(["sync_data"]);

    await switchView("calendar");
    expect.verifySteps(["sync_data"]);

    deferred.resolve();
    await animationFrame();
    expect.verifySteps(["search_read"]);
});

const SYNC_BUTTON_ARCH = `
    <calendar js_class="attendee_calendar" date_start="start" date_stop="stop">
        <field name="name"/>
    </calendar>
`;

test.tags("desktop");
test(`a provider's button hides once it reports synchronized`, async () => {
    onRpc("check_synchronization_status", async () => ({
        calendar_google: "sync_stopped",
    }));
    onRpc("/calendar_sync/google/sync_data", () => ({ status: "no_new_event" }));

    await mountView({
        type: "calendar",
        resModel: "calendar.event",
        arch: SYNC_BUTTON_ARCH,
    });

    expect(`#google_sync_pending`).toHaveCount(0);
});

test.tags("desktop");
test(`a provider's button shows while authorization is needed`, async () => {
    onRpc("check_synchronization_status", async () => ({
        calendar_google: "sync_stopped",
    }));
    onRpc("/calendar_sync/google/sync_data", () => ({ status: "need_auth" }));

    await mountView({
        type: "calendar",
        resModel: "calendar.event",
        arch: SYNC_BUTTON_ARCH,
    });

    expect(`#google_sync_pending`).toHaveCount(1);
});

test.tags("desktop");
test(`each configured provider offers its own button`, async () => {
    onRpc("calendar_sync_providers", () => [GOOGLE, OUTLOOK]);
    onRpc("/calendar/check_credentials", async () => ({
        calendar_google: true,
        calendar_microsoft: true,
    }));
    onRpc("check_synchronization_status", async () => ({
        calendar_google: "sync_stopped",
        calendar_microsoft: "sync_stopped",
    }));
    onRpc("/calendar_sync/google/sync_data", () => ({ status: "need_auth" }));
    onRpc("/calendar_sync/microsoft/sync_data", () => ({ status: "need_auth" }));

    await mountView({
        type: "calendar",
        resModel: "calendar.event",
        arch: SYNC_BUTTON_ARCH,
    });

    expect(`#synchronize_with`).toHaveCount(1);
    expect(`#google_sync_pending`).toHaveText("Google");
    expect(`#microsoft_sync_pending`).toHaveText("Outlook");
});

test.tags("desktop");
test(`stopping a synchronization stops that provider and shows it`, async () => {
    let status = "sync_active";
    onRpc("check_synchronization_status", async () => ({ calendar_google: status }));
    onRpc("calendar_sync_stop", ({ args }) => {
        expect.step(`stop ${args[1]}`);
        status = "sync_stopped";
        return true;
    });

    await mountView({
        type: "calendar",
        resModel: "calendar.event",
        arch: SYNC_BUTTON_ARCH,
    });
    expect(`#google_calendar_sync #check_text`).toHaveText("Google");

    await contains(`#google_calendar_sync button`).click();

    expect.verifySteps(["stop google"]);
    expect(`#google_calendar_sync #check_text`).toHaveCount(0);
});

test.tags("desktop");
test(`a paused synchronization is stopped for the user, never unpaused for all`, async () => {
    onRpc("check_synchronization_status", async () => ({
        calendar_google: "sync_paused",
    }));
    onRpc("/calendar_sync/google/sync_data", () => ({ status: "sync_paused" }));
    onRpc("calendar_sync_stop", ({ args }) => {
        expect.step(`stop ${args[1]}`);
        return true;
    });
    onRpc("unpause_google_synchronization", () => expect.step("unpause"));

    await mountView({
        type: "calendar",
        resModel: "calendar.event",
        arch: SYNC_BUTTON_ARCH,
    });
    await contains(`#header_synchronization_settings .o_calendar_pause`).click();

    expect.verifySteps(["stop google"]);
});
