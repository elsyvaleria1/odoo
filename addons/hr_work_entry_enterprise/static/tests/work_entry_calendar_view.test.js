import { defineHrWorkEntryModels } from "@hr_work_entry/../tests/hr_work_entry_test_helpers";
import { WorkEntriesGanttController } from "@hr_work_entry_enterprise/work_entries_gantt_controller";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { animationFrame, mockDate } from "@odoo/hoot-mock";
import {
    findComponent,
    makeMockServer,
    mountView,
} from "@web/../tests/web_test_helpers";
import { parseISO } from "@web/core/l10n/dates";

describe.current.tags("desktop");
defineHrWorkEntryModels();

beforeEach(() => {
    mockDate("2025-01-01 12:00:00", +0);
});

function getGanttController(view) {
    return findComponent(view, (c) => c instanceof WorkEntriesGanttController);
}

test("Test work entry gantt without work entry type", async () => {
    const { env } = await makeMockServer();
    env["hr.work.entry"].create([
        {
            name: "Test Work Entry 0",
            employee_id: 100,
            work_entry_type_id: false,
            date: "2025-01-01",
            create_date: "2025-01-01",
            duration: 120,
        },
    ]);
    const gantt = await mountView({
        type: "gantt",
        resModel: "hr.work.entry",
        arch: `
            <gantt js_class="work_entries_gantt"
                   string="Work Entries"
                   date_start="date"
                   date_stop="date"
                   color="color"
                   create="0"
                   default_group_by="employee_id"
                   decoration-warning="state == 'conflict'"
                   pill_label="True"
                   scales="week,month"
                   default_range="month"
                   total_row="1"
                   progress_bar="employee_id"
                   precision="{'week': 'day:full', 'month': 'day:full'}"
                   multi_create_view="multi_create_form"
                   plan="0">
                <field name="state"/>
            </gantt>`,
    });
    expect(".o_gantt_renderer").toBeDisplayed({
        message:
            "Gantt view should be displayed even with work entries with false work entry type",
    });
    const controller = getGanttController(gantt);
    const data = {
        name: "Test New Work Entry",
        employee_id: 100,
        work_entry_type_id: false,
        create_date: "2025-01-01",
    };
    const cellInfo = {
        rowId: JSON.stringify([{ employee_id: [100, "Richard"] }]),
        start: parseISO("2025-01-02"),
        stop: parseISO("2025-01-03"),
    };
    await controller.model.multiCreateRecords(
        {
            record: {
                getChanges: () => data,
            },
        },
        [cellInfo],
    );
    await animationFrame();
    expect(".o_gantt_pill").toHaveCount(2, {
        message: "2 work entries should be displayed in the gantt view",
    });
});

test("the sample work entries render when no progress bar was fetched", async () => {
    await makeMockServer();
    await mountView({
        type: "gantt",
        resModel: "hr.work.entry",
        arch: `
            <gantt js_class="work_entries_gantt" date_start="date" date_stop="date"
                   default_group_by="employee_id" progress_bar="employee_id" sample="1"
                   scales="week,month" default_range="month">
                <field name="state"/>
            </gantt>`,
    });
    expect(".o_gantt_view .o_view_sample_data").toHaveCount(1);
    expect(".o_gantt_pill").not.toHaveCount(0, {
        message: "sample pills are enriched without an employee progress bar to read",
    });
});
