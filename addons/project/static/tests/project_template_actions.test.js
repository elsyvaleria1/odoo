import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { animationFrame, queryAllTexts } from "@odoo/hoot-dom";
import {
    contains,
    defineActions,
    getService,
    mountWebClient,
    onRpc,
    patchWithCleanup,
    toggleActionMenu,
    toggleMenuItem,
} from "@web/../tests/web_test_helpers";
import { useServiceProtectMethodHandling } from "@web/core/utils/hooks";

import { defineProjectModels, ProjectProject } from "./project_models.js";

defineProjectModels();
describe.current.tags("desktop");

const CONVERT_TO_TEMPLATE = {
    id: 77,
    name: "Convert to Template",
    type: "ir.actions.server",
};

beforeEach(() => {
    patchWithCleanup(useServiceProtectMethodHandling, {
        fn() {
            expect.step("service call from a destroyed component");
            return super.fn();
        },
    });
    defineActions([
        CONVERT_TO_TEMPLATE,
        {
            id: 1,
            name: "Projects",
            res_model: "project.project",
            res_id: 1,
            views: [[false, "form"]],
        },
    ]);
    ProjectProject._toolbar = { action: [CONVERT_TO_TEMPLATE], print: [] };
    onRpc("/web/action/run", () => ({
        type: "ir.actions.client",
        tag: "project_to_template_redirection_action",
        params: { project_id: 1 },
    }));
    onRpc(
        "project.project",
        "action_create_template_from_project",
        function ({ args }) {
            expect.step("action_create_template_from_project");
            const templateId = this.env["project.project"].create({
                name: "Project 1 (template)",
                is_template: true,
            });
            return {
                type: "ir.actions.client",
                tag: "project_template_show_notification",
                params: {
                    project_id: templateId,
                    undo_method: "action_undo_create_template_from_project",
                    undo_args: [args[0], templateId, {}],
                    removes_record: true,
                },
            };
        },
    );
    onRpc(
        "project.project",
        "action_undo_create_template_from_project",
        function ({ args }) {
            expect.step("action_undo_create_template_from_project");
            this.env["project.project"].unlink([args[1]]);
            return {
                type: "ir.actions.client",
                tag: "display_notification",
                params: { type: "success", message: "Template converted back" },
            };
        },
    );
});

test("creating a template from the form opens the template and offers an undo", async () => {
    await mountWebClient();
    await getService("action").doAction(1);

    await toggleActionMenu();
    await toggleMenuItem("Convert to Template");
    await animationFrame();

    expect.verifySteps(["action_create_template_from_project"]);
    expect(
        queryAllTexts(".o_breadcrumb .breadcrumb-item, .o_breadcrumb .active"),
    ).toEqual(["Project 1", "Project 1 (template)"]);
    expect(".o_notification button:contains(Undo)").toHaveCount(1);
});

test("undoing the template returns to the project it came from", async () => {
    await mountWebClient();
    await getService("action").doAction(1);
    await toggleActionMenu();
    await toggleMenuItem("Convert to Template");
    await animationFrame();
    expect.verifySteps(["action_create_template_from_project"]);

    await contains(".o_notification button:contains(Undo)").click();
    await animationFrame();

    expect.verifySteps(["action_undo_create_template_from_project"]);
    expect(
        queryAllTexts(".o_breadcrumb .breadcrumb-item, .o_breadcrumb .active"),
    ).toEqual(["Project 1"]);
    expect(".o_notification:contains(Template converted back)").toHaveCount(1);
});
