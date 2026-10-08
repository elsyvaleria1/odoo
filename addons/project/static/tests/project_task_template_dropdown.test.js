import { beforeEach, expect, test } from "@odoo/hoot";
import { animationFrame, hover, queryAllTexts } from "@odoo/hoot-dom";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { ProjectTaskTemplateDropdown } from "@project/views/components/project_task_template_dropdown";
import { ProjectTemplateDropdown } from "@project/views/components/project_template_dropdown";
import {
    contains,
    mockService,
    mountView,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";

import { defineProjectModels, ProjectProject, ProjectTask } from "./project_models.js";

defineProjectModels();

function addTemplateTasks() {
    ProjectTask._records.push(
        {
            id: 4,
            name: "Template Task 1",
            project_id: 1,
            step_id: 1,
            state: "in_progress",
            is_template: true,
        },
        {
            id: 5,
            name: "Template Task 2",
            project_id: 1,
            step_id: 1,
            state: "in_progress",
            is_template: true,
        },
    );
}

beforeEach(() => {
    ProjectTask._views = {
        form: `
            <form js_class="project_task_form">
                <field name="name"/>
            </form>
        `,
        kanban: `
            <kanban js_class="project_task_kanban">
                <templates>
                    <t t-name="card">
                        <field name="name"/>
                    </t>
                </templates>
            </kanban>
        `,
        list: `
            <list js_class="project_task_list">
                <field name="name"/>
            </list>
        `,
    };
});

for (const [viewType, newButtonClass] of [
    ["form", ".o_form_button_create"],
    ["kanban", ".o-kanban-button-new"],
    ["list", ".o_list_button_add"],
]) {
    test(`template dropdown in ${viewType} view of a project with no template`, async () => {
        await mountView({
            resModel: "project.task",
            resId: 1,
            type: viewType,
            context: {
                default_project_id: 1,
            },
        });
        expect(newButtonClass).toHaveCount(1, {
            message: "The “New” button should be displayed",
        });
        expect(newButtonClass).not.toHaveClass("dropdown-toggle", {
            message:
                "The “New” button should not be a dropdown since there is no template",
        });

        await contains(`${newButtonClass}`).click();
    });

    test(`template dropdown in ${viewType} view of a project with one template with showing Edit and Delete actions`, async () => {
        addTemplateTasks();

        onRpc(({ method }) => {
            if (method === "unlink") {
                expect.step(method);
            }
        });

        mockService("action", {
            doAction(action) {
                if (action.res_id === 4 && action.res_model === "project.task") {
                    expect.step("task template opened");
                }
            },
        });

        await mountView({
            resModel: "project.task",
            resId: 1,
            type: viewType,
            context: {
                default_project_id: 1,
            },
        });
        expect(newButtonClass).toHaveCount(1, {
            message: "The “New” button should be displayed",
        });
        expect(newButtonClass).toHaveClass("dropdown-toggle", {
            message: "The “New” button should be a dropdown since there is a template",
        });

        await contains(newButtonClass).click();
        expect("button.dropdown-item:contains('New Task')").toHaveCount(1, {
            message: "The “New Task” button should be in the dropdown",
        });
        expect("button.dropdown-item:contains('Template Task 1')").toHaveCount(1, {
            message: "There should be a button named after the task template",
        });

        await hover("button.dropdown-item:contains('Template Task 1')");
        await animationFrame();

        await contains(".o_template_icon_group:first > i.fa-trash-can").click();
        expect(".modal-body").toHaveCount(1, {
            message: "A confirmation modal should appear when deleting a template",
        });

        await contains(".modal-footer .btn-primary").click();
        expect.verifySteps(["unlink"]);

        await animationFrame();
        await contains(".o_template_icon_group:first > i.fa-pencil").click();
        expect.verifySteps(["task template opened"]);
    });
}

test("template dropdown should not appear when not in the context of a specific project", async () => {
    addTemplateTasks();
    await mountView({
        resModel: "project.task",
        type: "kanban",
    });

    expect(".o-kanban-button-new").not.toHaveClass("dropdown-toggle", {
        message:
            "The “New” button should not be a dropdown since there is no project in the context",
    });
});

test("a user outside the project manager group gets the templates without edit and delete buttons", async () => {
    addTemplateTasks();
    onRpc("has_group", ({ args }) => {
        if (args[1] === "project.group_project_manager") {
            expect.step("has_group:project.group_project_manager");
            return false;
        }
        return true;
    });
    await mountView({
        resModel: "project.task",
        type: "list",
        context: { default_project_id: 1 },
    });
    await contains(".o_list_button_add").click();
    expect("button.dropdown-item:contains('Template Task 1')").toHaveCount(1);
    expect("button.dropdown-item:contains('Template Task 2')").toHaveCount(1);
    expect(".o_template_icon_group").toHaveCount(0, {
        message: "no edit/delete buttons, and no empty component in their place",
    });
    expect(".o-task-template").not.toHaveClass("pe-0");
    expect.verifySteps(["has_group:project.group_project_manager"], {
        message: "the group is asked once per dropdown, not once per template",
    });
});

test("the task template dropdown follows a projectId change", async () => {
    addTemplateTasks();
    ProjectTask._records.push({
        id: 6,
        name: "Template of project 2",
        project_id: 2,
        step_id: 1,
        is_template: true,
    });
    onRpc("project.project", "get_template_tasks", ({ args }) => {
        expect.step(`templates of ${args[0]}`);
    });

    class Parent extends Component {
        static components = { ProjectTaskTemplateDropdown };
        static props = null;
        static template = xml`
            <ProjectTaskTemplateDropdown
                projectId="this.state.projectId"
                newButtonClasses="'btn o_new'"
                onCreate="() => {}"
                context="{}"/>`;
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy({ projectId: 1 });
        }
    }

    const parent = await mountWithCleanup(Parent);
    await contains(".o_new").click();
    expect(queryAllTexts(".o-task-template")).toEqual([
        "Template Task 1",
        "Template Task 2",
    ]);
    await contains(".o_new").click();

    parent.state.projectId = 2;
    await animationFrame();
    await contains(".o_new").click();
    expect(queryAllTexts(".o-task-template")).toEqual(["Template of project 2"]);
    await contains(".o_new").click();

    parent.state.projectId = false;
    await animationFrame();
    expect(".o_new").not.toHaveClass("dropdown-toggle");
    expect.verifySteps(["templates of 1", "templates of 2"]);
});

test("the project template dropdown creates from the chosen template with the merged context", async () => {
    ProjectProject._records.push({
        id: 10,
        name: "Template Project",
        is_template: true,
    });
    onRpc(
        "wizard.project.project.create.from.template",
        "action_view_template_view",
        ({ kwargs }) => {
            const { template_id, template_name, from_parent, extra } = kwargs.context;
            expect.step({ template_id, template_name, from_parent, extra });
            return { type: "ir.actions.act_window_close" };
        },
    );

    class Parent extends Component {
        static components = { ProjectTemplateDropdown };
        static props = null;
        static template = xml`
            <ProjectTemplateDropdown
                newButtonClasses="'btn o_new'"
                onCreate="() => {}"
                context="{ from_parent: 1 }"
                getAdditionalContext="() => ({ extra: 2 })"/>`;
        props = useProps(this.constructor.props);
    }

    await mountWithCleanup(Parent);
    await contains(".o_new").click();
    expect(queryAllTexts(".o-project-template")).toEqual(["Template Project"]);
    await contains(".o-project-template").click();
    expect.verifySteps([
        {
            template_id: 10,
            template_name: "Template Project",
            from_parent: 1,
            extra: 2,
        },
    ]);
});
