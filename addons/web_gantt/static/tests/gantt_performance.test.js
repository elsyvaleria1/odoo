import { describe, expect, test } from "@odoo/hoot";
import { mockDate } from "@odoo/hoot-mock";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { GanttModel } from "@web_gantt/gantt_model";

import { defineGanttModels, ResUsers, Tasks } from "./gantt_mock_models.js";
import { mountGanttView } from "./web_gantt_test_helpers.js";

describe.current.tags("desktop");

defineGanttModels();

const MOUNT_BUDGET_MS = 5000;

test("mounting a grouped gantt is not quadratic in rows x records", async () => {
    mockDate("2018-12-20T08:00:00", +1);

    const NB_USERS = 500;
    const NB_TASKS = 10000;
    ResUsers._records = [...Array(NB_USERS)].map((_, i) => ({
        id: i + 1,
        name: `User ${i + 1}`,
    }));
    Tasks._records = [...Array(NB_TASKS)].map((_, i) => {
        const day = String((i % 27) + 1).padStart(2, "0");
        const nextDay = String((i % 27) + 2).padStart(2, "0");
        return {
            id: i + 1,
            name: `Task ${i + 1}`,
            user_id: (i % NB_USERS) + 1,
            start: `2018-12-${day} 00:00:00`,
            stop: `2018-12-${nextDay} 00:00:00`,
        };
    });

    let model;
    patchWithCleanup(GanttModel.prototype, {
        setup() {
            super.setup(...arguments);
            model = this;
        },
    });

    const before = performance.now();
    await mountGanttView({
        resModel: "tasks",
        arch: `<gantt date_start="start" date_stop="stop"/>`,
        groupBy: ["user_id"],
    });
    const elapsed = performance.now() - before;

    expect(model.data.rows).toHaveLength(NB_USERS);
    expect(model.data.records).toHaveLength(NB_TASKS);
    expect(elapsed).toBeLessThan(MOUNT_BUDGET_MS, {
        message: `mounting ${NB_TASKS} records over ${NB_USERS} groups took ${Math.round(elapsed)}ms`,
    });
});
