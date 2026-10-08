import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-dom";
import { setupChartJsForTests } from "@web/../tests/views/graph/graph_test_helpers";
import {
    contains,
    getFacetTexts,
    getService,
    mountView,
    mountWithCleanup,
    onRpc,
    removeFacet,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";

import { defineProjectModels, ProjectTask } from "./project_models.js";

defineProjectModels();
setupChartJsForTests();
describe.current.tags("desktop");

const searchViewArch = `
    <search>
        <field name="name"/>
        <filter name="conflict_task" string="Tasks in Conflict"
            context="{'highlight_conflicting_task': 1}"/>
    </search>`;

function mockConflictingTasks(ids) {
    onRpc("project.task", "search", ({ args }) => {
        expect.step(`search ${JSON.stringify(args[0])}`);
        return ids;
    });
}

const CONFLICT_SEARCH = 'search [["planning_overlap","!=",false]]';

test("the conflict filter restricts the list to the conflicting tasks", async () => {
    mockConflictingTasks([1]);
    const taskCount = ProjectTask._records.length;

    await mountView({
        resModel: "project.task",
        type: "list",
        arch: `<list js_class="project_task_list"><field name="name"/></list>`,
        searchViewArch,
        context: { search_default_conflict_task: 1 },
    });

    expect(getFacetTexts()).toEqual(["Tasks in Conflict"]);
    expect(".o_data_row").toHaveCount(1);
    expect.verifySteps([CONFLICT_SEARCH]);

    await removeFacet("Tasks in Conflict");
    expect(".o_data_row").toHaveCount(taskCount);
    expect.verifySteps([]);
});

test("no conflicting task leaves the conflict filter empty", async () => {
    mockConflictingTasks([]);

    await mountView({
        resModel: "project.task",
        type: "list",
        arch: `<list js_class="project_task_list"><field name="name"/></list>`,
        searchViewArch,
        context: { search_default_conflict_task: 1 },
    });

    expect(".o_data_row").toHaveCount(0);
    expect.verifySteps([CONFLICT_SEARCH]);
});

for (const [type, method] of [
    ["pivot", "formatted_read_grouping_sets"],
    ["graph", "formatted_read_group"],
]) {
    test(`the conflict filter restricts the ${type} view`, async () => {
        mockConflictingTasks([1, 2]);
        const domains = [];
        onRpc("project.task", method, ({ kwargs }) => {
            domains.push(JSON.stringify(kwargs.domain));
        });

        await mountView({
            resModel: "project.task",
            type,
            arch: `<${type} js_class="project_task_${type}"><field name="project_id"/></${type}>`,
            searchViewArch,
            context: { search_default_conflict_task: 1 },
        });

        expect.verifySteps([CONFLICT_SEARCH]);
        expect(domains.length).toBeGreaterThan(0);
        for (const domain of domains) {
            expect(domain).toInclude('["id","in",[1,2]]');
        }
    });
}

test("the conflicting ids survive a switch between task views without a new search", async () => {
    mockConflictingTasks([1]);
    ProjectTask._views = {
        list: `<list js_class="project_task_list"><field name="name"/></list>`,
        kanban: `
            <kanban js_class="project_task_kanban">
                <templates>
                    <t t-name="card"><field name="name"/></t>
                </templates>
            </kanban>`,
        form: `<form><field name="name"/></form>`,
        search: searchViewArch,
    };

    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        name: "Tasks",
        res_model: "project.task",
        type: "ir.actions.act_window",
        views: [
            [false, "list"],
            [false, "kanban"],
            [false, "form"],
        ],
        context: { search_default_conflict_task: 1 },
    });
    expect(".o_data_row").toHaveCount(1);
    expect.verifySteps([CONFLICT_SEARCH]);

    await contains(".o_switch_view.o_kanban").click();
    expect(getFacetTexts()).toEqual(["Tasks in Conflict"]);
    expect(".o_kanban_record:not(.o_kanban_ghost)").toHaveCount(1);
    expect.verifySteps([]);

    await contains(".o_kanban_record").click();
    expect(".o_form_view").toHaveCount(1);
    await contains(".o_back_button, .breadcrumb-item a").click();
    await animationFrame();
    expect(getFacetTexts()).toEqual(["Tasks in Conflict"]);
    expect(".o_kanban_record:not(.o_kanban_ghost)").toHaveCount(1);
    expect.verifySteps([CONFLICT_SEARCH], {
        message: "the form's plain search model does not carry the ids back",
    });
});
