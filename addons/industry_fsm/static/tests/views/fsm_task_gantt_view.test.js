import { beforeEach, expect, test } from "@odoo/hoot";
import { click, queryFirst } from "@odoo/hoot-dom";
import { animationFrame, mockDate } from "@odoo/hoot-mock";
import { defineProjectModels, projectModels } from "@project/../tests/project_models";
import { mockService, mountView } from "@web/../tests/web_test_helpers";
import { formatValue, now as getNow } from "@web/core/l10n/dates";

defineProjectModels();

function mockActionService(doActionStep) {
    const fakeActionService = {
        doAction: async (actionRequest, options = {}) => {
            expect(actionRequest).toBe(
                "industry_fsm.project_task_fsm_mobile_server_action",
            );
            expect.step(doActionStep);
        },
    };
    mockService("action", fakeActionService);
}

const { ProjectTask } = projectModels;

beforeEach(() => {
    mockDate("2024-01-03 07:00:00");
    ProjectTask._records = [
        {
            id: 1,
            name: "Custom Mobile Button Test",
            date_start: "2024-01-01 06:00:00",
            date_end: "2024-01-02 12:30:00",
        },
    ];

    ProjectTask._views = {
        form: `
            <form>
                <field name="name"/>
                <field name="date_start"/>
                <field name="date_end"/>
            </form>
        `,
    };
});

test.tags("desktop");
test("fsm task gantt view", async () => {
    const now = getNow();

    await mountView({
        resModel: "project.task",
        arch: '<gantt date_start="date_start" date_stop="date_end" js_class="task_gantt" />',
        type: "gantt",
        context: { fsm_mode: true },
    });

    expect(".o_gantt_view").toHaveCount(1);
    expect(".modal").toHaveCount(0);
    await click(".o_gantt_button_add.btn-primary");
    await animationFrame();
    expect(".modal").toHaveCount(1);
    expect(".modal .o_field_widget[name=date_start] .o_input").toHaveValue(
        formatValue(now, "MM/dd/yyyy 00:00:00"),
        {
            message:
                "The fsm_mode present in the view context should set the start_datetime to the current day instead of the first day of the gantt view",
        },
    );
});

test.tags("mobile");
test("test custom action for edit gantt popover button", async () => {
    const doActionStep = "doAction";
    mockActionService(doActionStep);

    await mountView({
        arch: '<gantt date_start="date_start" date_stop="date_end" js_class="fsm_task_gantt" />',
        resModel: "project.task",
        type: "gantt",
        context: { fsm_mode: true },
    });

    expect(".o_gantt_pill").toHaveCount(1);
    click(".o_gantt_pill");
    await animationFrame();
    expect(queryFirst(".o_popover .popover-body span")).toHaveText(
        "Custom Mobile Button Test",
    );
    click(".o_popover .popover-footer button", { text: "Edit" });
    await animationFrame();

    expect.verifySteps([doActionStep]);
});
