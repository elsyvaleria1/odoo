import { describe, expect, test } from "@odoo/hoot";
import { mockDate } from "@odoo/hoot-mock";
import { defineProjectModels } from "@project/../tests/project_models";
import { ProjectTask } from "@project_gantt/../tests/task_gant_model";
import { clickDate } from "@web/../tests/views/calendar/calendar_test_helpers";
import { mountView, onRpc } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineProjectModels();
onRpc("has_access", () => true);

test("Fsm task calendar view", async () => {
    mockDate("2024-01-03 12:00:00", 0);
    ProjectTask._views.form = `
        <form>
            <field name="id"/>
            <field name="name"/>
            <field name="date_start"/>
            <field name="date_end" widget="daterange" options="{'start_date_field': 'date_start'}"/>
        </form>
    `;
    await mountView({
        resModel: "project.task",
        type: "calendar",
        arch: `
            <calendar
                date_start="date_start_effective"
                date_stop="date_end"
                event_open_popup="1"
                mode="month"
                js_class="fsm_task_calendar"
                quick_create="0"
            />
        `,
    });

    expect(".o_calendar_view").toHaveCount(1);

    await clickDate("2024-01-09");

    expect("div[name='date_start'] button").toHaveValue("01/09/2024 00:00:00", {
        message:
            "The date_start field should hold the date_start_effective value in the record thanks to the fsmCalendarModel makeContextDefault inheritance",
    });
});
