import { GanttEmployeeAvatar } from "@hr_gantt/hr_gantt_employee_avatar";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { click, queryAll } from "@odoo/hoot-dom";
import { animationFrame, mockDate } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    models,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { mountGanttView } from "@web_gantt/../tests/web_gantt_test_helpers";

describe.current.tags("desktop");

class Employee extends models.Model {
    _name = "hr.employee";

    _records = [
        { id: 1, display_name: "Mario" },
        { id: 2, display_name: "Luigi" },
        { id: 3, display_name: "Yoshi" },
    ];
}

class Task extends models.Model {
    start = fields.Datetime();
    stop = fields.Datetime();
    employee_id = fields.Many2one({ relation: "hr.employee" });
    manager_id = fields.Many2one({ relation: "hr.employee" });
    foo = fields.Char();

    _records = [
        {
            id: 1,
            display_name: "Task 1",
            start: "2018-11-30 18:30:00",
            stop: "2018-12-31 18:29:59",
            employee_id: 1,
            manager_id: 2,
            foo: "Foo 1",
        },
        {
            id: 2,
            display_name: "Task 2",
            start: "2018-12-17 11:30:00",
            stop: "2018-12-22 06:29:59",
            employee_id: 2,
            foo: "Foo 2",
        },
        {
            id: 3,
            display_name: "Task 3",
            start: "2018-12-27 06:30:00",
            stop: "2019-01-03 06:29:59",
            employee_id: 3,
            foo: "Foo 1",
        },
        {
            id: 4,
            display_name: "Task 4",
            start: "2018-12-19 18:30:00",
            stop: "2018-12-20 06:29:59",
            employee_id: 1,
            foo: "Foo 3",
        },
        {
            id: 5,
            display_name: "Task 5",
            start: "2018-12-21 10:30:00", // 11:30:00 CET
            stop: "2018-12-21 11:29:59", // 12:29:59 CET
            employee_id: 1,
            foo: "Foo 3",
        },
        {
            id: 6,
            display_name: "Task 6",
            start: "2018-12-22 10:30:00", // 11:30:00 CET
            stop: "2018-12-22 11:59:59", // 12:59:59 CET
            employee_id: 1,
            foo: "Foo 3",
        },
    ];
}

class Leave extends models.Model {
    date_from = fields.Date();
    date_to = fields.Date();
    employee_id = fields.Many2one({ relation: "hr.employee" });

    _records = [
        {
            id: 1,
            display_name: "Leave 1",
            date_from: "2018-12-21",
            date_to: "2018-12-21",
            employee_id: 1,
        },
    ];
}

defineMailModels();
defineModels([Employee, Task, Leave]);

const arch = `<gantt js_class="hr_gantt" date_start="start" date_stop="stop" />`;

beforeEach(() => {
    mockDate("2018-12-20 07:00:00", +1);
});

test("hr gantt view not grouped", async () => {
    await mountGanttView({ resModel: "task", arch });
    expect(".o-mail-Avatar").toHaveCount(0);
});

test("hr gantt view grouped by a differently-named employee many2one", async () => {
    // Regression test for the fix in commit 4a9c1fbef3: avatar-row detection
    // must key off the grouped field's relation, not its literal name.
    await mountGanttView({ resModel: "task", arch, groupBy: ["manager_id"] });
    expect(".o_gantt_row_title .o-mail-Avatar").toHaveCount(1);
});

test("hr gantt view grouped by employee only", async () => {
    await mountGanttView({ resModel: "task", arch, groupBy: ["employee_id"] });
    expect(".o_gantt_row_title .o-mail-Avatar").toHaveCount(3);
});

test("hr gantt view grouped by employee > foo", async () => {
    await mountGanttView({ resModel: "task", arch, groupBy: ["employee_id", "foo"] });
    expect(
        ".o_gantt_row_header.o_gantt_group .o_gantt_row_title .o-mail-Avatar",
    ).toHaveCount(3);
});

test("hr gantt view grouped by foo > employee", async () => {
    await mountGanttView({ resModel: "task", arch, groupBy: ["foo", "employee_id"] });
    expect(
        ".o_gantt_row_header:not(.o_gantt_group) .o_gantt_row_title .o-mail-Avatar",
    ).toHaveCount(4);
});

test("hr gantt view pill rounding", async () => {
    expect.assertions(7);
    await mountGanttView({ resModel: "task", arch });
    const [task4, task5, task6] = queryAll(".o_gantt_pill_wrapper.o_draggable").reduce(
        (acc, node) =>
            ["task,4", "task,5", "task,6"].includes(node.innerText)
                ? acc.concat(node.getBoundingClientRect())
                : acc,
        [],
    );
    const [col19, col20, col21, col22] = queryAll(".o_gantt_header_cell").reduce(
        (acc, node) =>
            "19" <= node.innerText && node.innerText <= "22"
                ? acc.concat(node.getBoundingClientRect())
                : acc,
        [],
    );
    expect(task4.width).toBe(col19.width, {
        message: "Task 4 should take up 2 half-days",
    });
    expect(task5.width).toBe(col21.width / 2, {
        message: "Task 5 should take up 1 half-day",
    });
    expect(task6.width).toBe(col22.width / 2, {
        message: "Task 6 should take up 1 half-day",
    });
    expect(task4.left).toBeWithin(col19.x, col20.x, {
        message: "Task 4 should start the 19th",
    });
    expect(task4.right).toBeWithin(col20.x, col21.x, {
        message: "Task 4 should end the 20th",
    });
    expect(task5.left).toBe(col21.left, {
        message: "Task 5 should display before noon",
    });
    expect(task6.right).toBe(col22.right, {
        message: "Task 6 should display after noon",
    });
});

test("clicking a row avatar opens the employee card", async () => {
    const calls = [];
    onRpc("hr.employee", "get_avatar_card_data", ({ model }) => {
        calls.push(model);
        return [{ id: 1, name: "Mario" }];
    });
    await mountGanttView({ resModel: "task", arch, groupBy: ["employee_id"] });
    await click(".o_gantt_row_title .o-mail-Avatar img");
    await animationFrame();
    expect(calls).toEqual(["hr.employee"]);
});

test("canOpenPopover=false suppresses the employee card", async () => {
    // The base Avatar contract: this prop must disable the popover AND its
    // RPC (audit rows H1-r4/J2-r4 — openCard used to ignore it).
    let called = false;
    onRpc("hr.employee", "get_avatar_card_data", () => {
        called = true;
        return [{ id: 1, name: "Mario" }];
    });
    await mountWithCleanup(GanttEmployeeAvatar, {
        props: { resId: 1, resModel: "hr.employee", canOpenPopover: false },
    });
    await click(".o-mail-Avatar img");
    await animationFrame();
    expect(called).toBe(false);
    expect(".o_avatar_card").toHaveCount(0);
});

test("a one-day pill on date fields takes the whole day, not half of it", async () => {
    await mountGanttView({
        resModel: "leave",
        arch: `<gantt js_class="hr_gantt" date_start="date_from" date_stop="date_to" />`,
    });
    const [leave] = queryAll(".o_gantt_pill_wrapper.o_draggable").map((node) =>
        node.getBoundingClientRect(),
    );
    const [col21] = queryAll(".o_gantt_header_cell")
        .filter((node) => node.innerText === "21")
        .map((node) => node.getBoundingClientRect());
    expect(leave.left).toBe(col21.left);
    expect(leave.width).toBe(col21.width);
});
