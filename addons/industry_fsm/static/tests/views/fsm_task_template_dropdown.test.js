import { expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { animationFrame, Deferred } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { defineProjectModels } from "@project/../tests/project_models";
import { ProjectTaskTemplateDropdown } from "@project/views/components/project_task_template_dropdown";
import {
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { useServiceProtectMethodHandling } from "@web/core/utils/hooks";

defineProjectModels();

test("an fsm template dropdown replaced while it loads does not fail its parent", async () => {
    patchWithCleanup(useServiceProtectMethodHandling, {
        fn: useServiceProtectMethodHandling.original,
    });
    const groupCheck = new Deferred();
    onRpc("has_group", () => groupCheck);
    onRpc("project.task", "search_read", () => {
        expect.step("fsm templates");
        return [];
    });

    class Parent extends Component {
        static components = { ProjectTaskTemplateDropdown };
        static props = null;
        static template = xml`
            <div class="o_parent">
                <ProjectTaskTemplateDropdown
                    t-if="this.state.show"
                    newButtonClasses="'btn'"
                    onCreate="() => {}"
                    context="{ fsm_mode: true }"/>
            </div>`;
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy({ show: false });
        }
    }

    const parent = await mountWithCleanup(Parent);
    parent.state.show = true;
    await animationFrame();
    parent.state.show = false;
    await animationFrame();
    groupCheck.resolve(true);
    await animationFrame();

    expect.verifySteps(["fsm templates"]);
    expect(".o_parent").toHaveCount(1);
});

test("an fsm template dropdown with no project offers the fsm task templates", async () => {
    onRpc("has_group", () => false);
    onRpc("project.task", "search_read", ({ kwargs }) => {
        expect.step("fsm templates");
        expect(kwargs.domain).toEqual([
            ["is_template", "=", true],
            ["is_fsm", "=", true],
        ]);
        return [{ id: 7, name: "Boiler service" }];
    });

    await mountWithCleanup(ProjectTaskTemplateDropdown, {
        props: {
            newButtonClasses: "btn",
            onCreate: () => {},
            context: { fsm_mode: true },
        },
    });
    expect.verifySteps(["fsm templates"]);
    await click("button.o-dropdown-caret");
    await animationFrame();
    expect(".o-task-template").toHaveText("Boiler service");
});
