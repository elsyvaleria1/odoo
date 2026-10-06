import { expect, test } from "@odoo/hoot";
import { queryAll } from "@odoo/hoot-dom";
import { mockDate } from "@odoo/hoot-mock";
import { defineProjectModels, projectModels } from "@project/../tests/project_models";
import { contains } from "@web/../tests/web_test_helpers";
import { mountGanttView } from "@web_gantt/../tests/web_gantt_test_helpers";

defineProjectModels();

test("Check progress bar values", async () => {
    mockDate("2020-06-12T08:00:00", +1);
    projectModels.ProjectProject._records = [{ id: 1, name: "My Project" }];
    projectModels.ProjectTask._records = [
        {
            id: 1,
            name: "Blop",
            date_start: "2020-06-14 08:00:00",
            date_end: "2020-06-24 08:00:00",
            progress: 50.0,
            project_id: 1,
        },
        {
            id: 2,
            name: "Yop",
            date_start: "2020-06-02 08:00:00",
            date_end: "2020-06-12 08:00:00",
            project_id: 1,
        },
    ];
    await mountGanttView({
        resModel: "project.task",
        arch: `<gantt js_class="task_gantt" date_start="date_start" date_stop="date_end" progress="progress"/>`,
    });
    await contains(".o_content").scroll({ left: 400 });
    const [firstPillFirstSpan, secondPillFirstSpan] = queryAll(
        ".o_gantt_pill span:first-child",
    );
    expect(firstPillFirstSpan).not.toHaveClass("o_gantt_progress");
    expect(secondPillFirstSpan).toHaveClass("o_gantt_progress");
    expect(secondPillFirstSpan.style.width).toBe("50%");
});
