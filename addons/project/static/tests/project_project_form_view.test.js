import { beforeEach, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import {
    clickSave,
    contains,
    MockServer,
    mockService,
    mountView,
    onRpc,
    patchWithCleanup,
    toggleActionMenu,
    toggleMenuItem,
} from "@web/../tests/web_test_helpers";
import { user } from "@web/core/user";

import {
    defineProjectModels,
    PROJECT_FEATURE_GROUPS,
    ProjectProject,
} from "./project_models.js";

defineProjectModels();

beforeEach(() => {
    ProjectProject._records = [
        {
            id: 1,
            name: "Project 1",
            allow_milestones: false,
            allow_dependencies: false,
            allow_recurring_tasks: false,
        },
        {
            id: 2,
            name: "Project 2",
            allow_milestones: false,
            allow_dependencies: false,
            allow_recurring_tasks: false,
        },
    ];

    patchWithCleanup(user, {
        async hasGroup(group) {
            const feature = Object.keys(PROJECT_FEATURE_GROUPS).find(
                (fName) => PROJECT_FEATURE_GROUPS[fName] === group,
            );
            if (feature) {
                return MockServer.env["project.project"].get_features_enabled()[
                    feature
                ];
            }
            return super.hasGroup(group);
        },
    });

    mockService("action", {
        doAction(actionRequest) {
            if (actionRequest === "reload_context") {
                expect.step("reload_context");
            } else {
                return super.doAction(...arguments);
            }
        },
    });
});

test("project.project (form)", async () => {
    await mountView({
        resModel: "project.project",
        resId: 1,
        type: "form",
        arch: `
            <form js_class="form_description_expander">
                <field name="name"/>
            </form>
        `,
    });
    expect(".o_form_view").toHaveCount(1);
});

const formViewParams = {
    resModel: "project.project",
    type: "form",
    actionMenus: {},
    resId: 1,
    arch: `
        <form js_class="project_project_form">
            <field name="active"/>
            <field name="name"/>
            <field name="allow_dependencies"/>
            <field name="allow_milestones"/>
            <field name="allow_recurring_tasks"/>
        </form>
    `,
};

onRpc("project.project", "get_features_groups", ({ method }) => expect.step(method));
onRpc("project.project", "get_features_enabled", ({ method }) => expect.step(method));

onRpc("web_save", ({ method }) => expect.step(method));

test("project.project (form) hide archive action for project user", async () => {
    onRpc("has_group", ({ args }) => args[1] === "project.group_project_user");
    await mountView(formViewParams);
    await toggleActionMenu();
    expect(`.o-dropdown--menu span:contains(Archive)`).toHaveCount(0, {
        message: "Archive action should not be visible",
    });
    expect.verifySteps(["get_features_groups"]);
});

test("project.project (form) show archive action for project manager", async () => {
    onRpc("has_group", () => true);
    await mountView(formViewParams);
    await toggleActionMenu();
    expect(`.o-dropdown--menu span:contains(Archive)`).toHaveCount(1, {
        message: "Arhive action should be visible",
    });
    await toggleMenuItem("Archive");
    await contains(`.modal-footer .btn-primary`).click();
    await toggleActionMenu();
    expect(`.o-dropdown--menu span:contains(Unarchive)`).toHaveCount(1, {
        message: "Unarchive action should be visible",
    });
    await toggleMenuItem("UnArchive");
    expect.verifySteps(["get_features_groups"]);
});

test("reload the page when allow_milestones is enabled on at least one project", async () => {
    await mountView(formViewParams);

    await click("div[name='allow_milestones'] input");
    await clickSave();

    expect.verifySteps([
        "get_features_groups",
        "web_save",
        "get_features_enabled",
        "reload_context",
    ]);
});

test("do not reload the page when allow_milestones is enabled and there already exists one project with the feature enabled", async () => {
    ProjectProject._records[1].allow_milestones = true;
    await mountView(formViewParams);

    await click("div[name='allow_milestones'] input");
    await clickSave();

    expect.verifySteps(["get_features_groups", "web_save", "get_features_enabled"]);
});

test("reload the page when allow_milestones is disabled on all projects", async () => {
    ProjectProject._records[0].allow_milestones = true;
    await mountView(formViewParams);

    await click("div[name='allow_milestones'] input");
    await clickSave();

    expect.verifySteps([
        "get_features_groups",
        "web_save",
        "get_features_enabled",
        "reload_context",
    ]);
});

test("reload the page when allow_dependencies is enabled on at least one project", async () => {
    await mountView(formViewParams);

    await click("div[name='allow_dependencies'] input");
    await clickSave();

    expect.verifySteps([
        "get_features_groups",
        "web_save",
        "get_features_enabled",
        "reload_context",
    ]);
});

test("do not reload the page when allow_dependencies is enabled and there already exists one project with the feature enabled", async () => {
    ProjectProject._records[1].allow_dependencies = true;
    await mountView(formViewParams);

    await click("div[name='allow_dependencies'] input");
    await clickSave();

    expect.verifySteps(["get_features_groups", "web_save", "get_features_enabled"]);
});

test("reload the page when allow_dependencies is disabled on all projects", async () => {
    ProjectProject._records[0].allow_dependencies = true;
    await mountView(formViewParams);

    await click("div[name='allow_dependencies'] input");
    await clickSave();

    expect.verifySteps([
        "get_features_groups",
        "web_save",
        "get_features_enabled",
        "reload_context",
    ]);
});

test("reload the page when allow_recurring_tasks is enabled on at least one project", async () => {
    await mountView(formViewParams);

    await click("div[name='allow_recurring_tasks'] input");
    await clickSave();

    expect.verifySteps([
        "get_features_groups",
        "web_save",
        "get_features_enabled",
        "reload_context",
    ]);
});

test("do not reload the page when allow_recurring_tasks is enabled and there already exists one project with the feature enabled", async () => {
    ProjectProject._records[1].allow_recurring_tasks = true;
    await mountView(formViewParams);

    await click("div[name='allow_recurring_tasks'] input");
    await clickSave();

    expect.verifySteps(["get_features_groups", "web_save", "get_features_enabled"]);
});

test("reload the page when allow_recurring_tasks is disabled on all projects", async () => {
    ProjectProject._records[0].allow_recurring_tasks = true;
    await mountView(formViewParams);

    await click("div[name='allow_recurring_tasks'] input");
    await clickSave();

    expect.verifySteps([
        "get_features_groups",
        "web_save",
        "get_features_enabled",
        "reload_context",
    ]);
});

test("do not reload the page when the user already held the feature group", async () => {
    patchWithCleanup(user, {
        async hasGroup(group) {
            return (
                group === PROJECT_FEATURE_GROUPS.allow_milestones ||
                super.hasGroup(group)
            );
        },
    });
    await mountView(formViewParams);

    await click("div[name='allow_milestones'] input");
    await clickSave();

    expect.verifySteps(["get_features_groups", "web_save", "get_features_enabled"]);
});

test("saving a field that is no feature asks the server nothing", async () => {
    await mountView(formViewParams);

    await contains("div[name='name'] input").edit("Renamed");
    await clickSave();

    expect.verifySteps(["get_features_groups", "web_save"]);
});
