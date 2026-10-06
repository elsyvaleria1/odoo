import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import {
    contains,
    defineModels,
    fields,
    getService,
    models,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";
import {
    editView,
    handleDefaultStudioRoutes,
} from "@web_studio/../tests/view_editor_tests_utils";

describe.current.tags("desktop");

defineMailModels();

const arch = `
    <grid string="Timesheets" hide_line_total="1">
        <field name="project" type="row"/>
        <field name="date" type="col">
            <range name="week" string="Week" span="week" step="day"/>
        </field>
        <field name="hours" type="measure"/>
    </grid>`;

class Task extends models.Model {
    _name = "task";

    project = fields.Char();
    date = fields.Date();
    hours = fields.Float();

    _records = [{ id: 1, project: "Foo", date: "2026-09-11", hours: 2 }];

    _views = {
        "grid,1": arch,
        search: "<search/>",
    };
}

defineModels([Task]);

handleDefaultStudioRoutes();

async function openGridEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        name: "Task",
        res_model: "task",
        type: "ir.actions.act_window",
        view_mode: "grid",
        views: [
            [1, "grid"],
            [false, "search"],
        ],
        group_ids: [],
    });
    await contains(".o_web_studio_navbar_item").click();
}

test("grid editor sidebar reads the root booleans off the arch", async () => {
    await openGridEditor();
    expect(
        ".o_web_studio_sidebar .o_web_studio_property_hide_line_total input",
    ).toBeChecked();
    expect(
        ".o_web_studio_sidebar .o_web_studio_property_hide_column_total input",
    ).not.toBeChecked();
    expect(
        ".o_web_studio_sidebar .o_web_studio_property_barchart_total input",
    ).not.toBeChecked();
});

test("toggling a root boolean writes the attribute", async () => {
    expect.assertions(2);
    onRpc("/web_studio/edit_view", async (request) => {
        const { params } = await request.json();
        expect(params.operations[0].new_attrs).toEqual({ hide_column_total: "1" });
        expect.step("edit_view");
        return editView(
            params,
            "grid",
            arch.replace("<grid ", '<grid hide_column_total="1" '),
        );
    });
    await openGridEditor();
    await contains(
        ".o_web_studio_sidebar .o_web_studio_property_hide_column_total input",
    ).click();
    expect.verifySteps(["edit_view"]);
});
