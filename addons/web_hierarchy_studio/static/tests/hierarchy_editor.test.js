import "@web_hierarchy/../tests/hierarchy_mock_server";

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
    <hierarchy parent_field="parent_id" child_field="child_ids" draggable="1">
        <templates>
            <t t-name="hierarchy-box">
                <div class="o_hierarchy_node_header"><field name="name"/></div>
            </t>
        </templates>
    </hierarchy>`;

class Employee extends models.Model {
    _name = "employee";

    name = fields.Char();
    parent_id = fields.Many2one({ relation: "employee" });
    child_ids = fields.One2many({ relation: "employee", relation_field: "parent_id" });

    _records = [
        { id: 1, name: "Boss" },
        { id: 2, name: "Report", parent_id: 1 },
    ];

    _views = {
        "hierarchy,1": arch,
        search: "<search/>",
    };
}

defineModels([Employee]);

handleDefaultStudioRoutes();

async function openHierarchyEditor() {
    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        name: "Employees",
        res_model: "employee",
        type: "ir.actions.act_window",
        view_mode: "hierarchy",
        views: [
            [1, "hierarchy"],
            [false, "search"],
        ],
        group_ids: [],
    });
    await contains(".o_web_studio_navbar_item").click();
}

test("hierarchy editor sidebar reads the root attributes off the arch", async () => {
    await openHierarchyEditor();
    expect(
        ".o_web_studio_sidebar .o_web_studio_property_parent_field input",
    ).toHaveValue("Parent (parent_id)");
    expect(
        ".o_web_studio_sidebar .o_web_studio_property_child_field input",
    ).toHaveValue("Childs (child_ids)");
    expect(
        ".o_web_studio_sidebar .o_web_studio_property_draggable input",
    ).toBeChecked();
});

test("toggling draggable writes the attribute", async () => {
    expect.assertions(2);
    onRpc("/web_studio/edit_view", async (request) => {
        const { params } = await request.json();
        expect(params.operations[0].new_attrs).toEqual({ draggable: "0" });
        expect.step("edit_view");
        return editView(
            params,
            "hierarchy",
            arch.replace('draggable="1"', 'draggable="0"'),
        );
    });
    await openHierarchyEditor();
    await contains(
        ".o_web_studio_sidebar .o_web_studio_property_draggable input",
    ).click();
    expect.verifySteps(["edit_view"]);
});
