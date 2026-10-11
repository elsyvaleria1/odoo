import { describe, expect, test } from "@odoo/hoot";
import { mockDate, mockTimeZone } from "@odoo/hoot-mock";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

import { defineGanttModels, Tasks } from "./gantt_mock_models.js";
import { mountGanttView } from "./web_gantt_test_helpers.js";

describe.current.tags("desktop");

defineGanttModels();

test("grid columns stay whole across a DST transition that removes midnight", async () => {
    mockTimeZone("America/Santiago");
    mockDate("2024-09-10T08:00:00");

    Tasks._records = [
        {
            id: 1,
            name: "Across the transition",
            start: "2024-09-08 12:00:00",
            stop: "2024-09-11 12:00:00",
        },
        {
            id: 2,
            name: "Starting on the transition day",
            start: "2024-09-08 04:00:00",
            stop: "2024-09-08 20:00:00",
        },
    ];

    const columns = [];
    patchWithCleanup(GanttRenderer.prototype, {
        getGridColumnFromDates() {
            const result = super.getGridColumnFromDates(...arguments);
            columns.push(result);
            return result;
        },
    });

    await mountGanttView({
        resModel: "tasks",
        arch: `<gantt date_start="start" date_stop="stop" default_range="month"/>`,
    });

    expect(columns.length).toBeGreaterThan(0);
    const fractional = columns.filter(
        ([a, b]) => !Number.isInteger(a) || !Number.isInteger(b),
    );
    expect(fractional).toEqual([], {
        message: `every grid column must name an existing line; got ${JSON.stringify(fractional)}`,
    });
    expect(".o_gantt_pill").toHaveCount(2);
});
