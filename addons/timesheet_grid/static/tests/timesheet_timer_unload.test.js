import { patchSession } from "@hr_timesheet/../tests/hr_timesheet_models";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { waitFor } from "@odoo/hoot-dom";
import { animationFrame, mockSendBeacon } from "@odoo/hoot-mock";
import { TimesheetTimerKanbanController } from "@timesheet_grid/views/timesheet_kanban/timesheet_timer_kanban_controller";
import { TimesheetTimerListController } from "@timesheet_grid/views/timesheet_list/timesheet_timer_list_controller";
import {
    contains,
    isPromptRequested,
    mountView,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

import { defineTimesheetModels, HRTimesheet } from "./hr_timesheet_models.js";
import {
    clickTimerButton,
    timerHeaderSelectors,
} from "./timesheet_grid_timer_helpers.js";

defineTimesheetModels();
beforeEach(() => {
    patchSession();
    HRTimesheet._views.kanban = `
        <kanban js_class="timesheet_timer_kanban">
            <templates>
                <field name="name"/>
                <t t-name="card">
                    <field name="project_id"/>
                    <field name="unit_amount"/>
                </t>
            </templates>
        </kanban>
    `;
});
describe.current.tags("desktop");

/**
 * @param {any} Controller
 * @returns {{ controller?: any }}
 */
function captureController(Controller) {
    const box = {};
    patchWithCleanup(Controller.prototype, {
        setup() {
            super.setup(...arguments);
            box.controller = this;
        },
    });
    return box;
}

/**
 * @param {{ type: "kanban" | "list", groupBy?: string[] }} params
 * @returns {Promise<any>} the view's controller, with the timer running
 */
async function mountWithRunningTimer({ type, groupBy = [] }) {
    const box = captureController(
        type === "kanban"
            ? TimesheetTimerKanbanController
            : TimesheetTimerListController,
    );
    await mountView({ type, resModel: HRTimesheet._name, groupBy });
    await waitFor(timerHeaderSelectors.start);
    await clickTimerButton("start");
    await waitFor(timerHeaderSelectors.stop);
    return box.controller;
}

/** @param {string} value */
async function describeTimerWithoutLeaving(value) {
    await contains("div.pinned_header div[name=name] input").edit(value, {
        confirm: false,
    });
}

test("kanban: closing the tab with an unsaved timer description asks to stay", async () => {
    const controller = await mountWithRunningTimer({ type: "kanban" });
    await describeTimerWithoutLeaving("unsaved");
    expect(await isPromptRequested((ev) => controller.beforeUnload(ev))).toBe(true);
});

test("kanban: closing the tab with an untouched running timer does not ask", async () => {
    const controller = await mountWithRunningTimer({ type: "kanban" });
    expect(await isPromptRequested((ev) => controller.beforeUnload(ev))).toBe(false);
});

test("grouped list: a timer description whose beacon is refused asks to stay", async () => {
    mockSendBeacon(() => false);
    const controller = await mountWithRunningTimer({
        type: "list",
        groupBy: ["project_id"],
    });
    await describeTimerWithoutLeaving("refused");
    expect(await isPromptRequested((ev) => controller.beforeUnload(ev))).toBe(true);
});

test("grouped list: a timer description the beacon carries lets the tab close", async () => {
    const written = [];
    mockSendBeacon((_route, blob) => {
        blob.text().then((text) => written.push(JSON.parse(text).params.args[1]));
        return true;
    });
    const controller = await mountWithRunningTimer({
        type: "list",
        groupBy: ["project_id"],
    });
    await describeTimerWithoutLeaving("carried");
    expect(await isPromptRequested((ev) => controller.beforeUnload(ev))).toBe(false);
    await animationFrame();
    expect(written).toEqual([{ name: "carried" }]);
});

test("list: a timer description whose beacon is refused asks to stay", async () => {
    mockSendBeacon(() => false);
    const controller = await mountWithRunningTimer({ type: "list" });
    await describeTimerWithoutLeaving("refused");
    expect(await isPromptRequested((ev) => controller.beforeUnload(ev))).toBe(true);
});
