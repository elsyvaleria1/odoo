import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { hover, pointerDown, pointerUp, queryAll, queryFirst } from "@odoo/hoot-dom";
import { animationFrame, mockDate } from "@odoo/hoot-mock";

import { defineGanttModels } from "./gantt_mock_models.js";
import { mountGanttView } from "./web_gantt_test_helpers.js";

describe.current.tags("desktop");

defineGanttModels();
beforeEach(() => {
    mockDate("2018-12-20T08:00:00", +1);
});

async function mountAndGetPills() {
    await mountGanttView({
        resModel: "tasks",
        arch: '<gantt date_start="start" date_stop="stop"/>',
    });
    return queryAll(".o_resizable");
}

const handleCount = () => document.querySelectorAll(".o_resize_handle").length;

test("hovering a pill reveals its resize handles", async () => {
    const pills = await mountAndGetPills();
    await hover(pills[0]);
    await animationFrame();
    expect(handleCount()).toBeGreaterThan(0);
});

test("handles follow the pointer from one pill to another", async () => {
    const pills = await mountAndGetPills();
    await hover(pills[0]);
    await animationFrame();
    await hover(pills[1]);
    await animationFrame();
    expect(handleCount()).toBeGreaterThan(0);
});

test("handles keep working after a handle is clicked but not dragged", async () => {
    const pills = await mountAndGetPills();
    await hover(pills[0]);
    await animationFrame();
    expect(handleCount()).toBeGreaterThan(0);

    // press+release on the handle without moving: willStartDrag runs, dragStart
    // never does, so nothing lowers `willDrag` again
    const handle = queryFirst(".o_resize_handle");
    await pointerDown(handle);
    await pointerUp(handle);
    await animationFrame();

    await hover(pills[1]);
    await animationFrame();
    expect(handleCount()).toBeGreaterThan(0);
});
