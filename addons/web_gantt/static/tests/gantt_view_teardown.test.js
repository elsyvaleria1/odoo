import { describe, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { animationFrame, mockDate, runAllTimers } from "@odoo/hoot-mock";
import {
    getService,
    mountWithCleanup,
    onRpc,
    switchView,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";

import { defineGanttModels, Tasks } from "./gantt_mock_models.js";
import { SELECTORS } from "./web_gantt_test_helpers.js";

describe.current.tags("desktop");

defineGanttModels();

test("leaving the view before a range change's debounce elapses", async () => {
    // The range change schedules a fetch 500ms out. Built with plain
    // `debounce` nothing cancelled it, and it ran against a torn-down
    // component: not a stray RPC but an uncaught `Error: Component is
    // destroyed`, which HOOT reports here as an unverified error.
    mockDate("2018-12-20T08:00:00", +1);
    Tasks._views = {
        gantt: `<gantt date_start="start" date_stop="stop"/>`,
        list: `<list><field name="name"/></list>`,
    };
    let calls = 0;
    onRpc("get_gantt_data", () => {
        calls++;
    });

    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        res_model: "tasks",
        type: "ir.actions.act_window",
        views: [
            [false, "gantt"],
            [false, "list"],
        ],
    });
    await animationFrame();
    expect(calls).toBe(1);

    await click(SELECTORS.scaleSelectorToggler);
    await animationFrame();
    await click(`${SELECTORS.scaleSelectorMenu} .dropdown-item:text(Year)`);
    await animationFrame();
    expect(calls).toBe(1, { message: "the fetch is still only scheduled" });

    await switchView("list");
    await animationFrame();
    await runAllTimers();
    await animationFrame();

    expect(calls).toBe(1, {
        message: "the scheduled fetch was cancelled with the component",
    });
});
