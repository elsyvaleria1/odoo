import { defineDocumentsModels } from "@document/../tests/document_test_helpers";
import { getEnrichedSearchArch } from "@document/../tests/helpers/views/search";
import { describe, expect, test } from "@odoo/hoot";
import { press } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { getService, mountView, onRpc } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineDocumentsModels();

test("the documents activity view mounts without a drag-and-drop wiring of its own", async () => {
    await mountView({
        type: "activity",
        resModel: "document.document",
        arch: `
            <activity string="Documents" js_class="documents_activity">
                <field name="folder_id"/>
                <templates>
                    <div t-name="activity-box">
                        <field name="name"/>
                    </div>
                </templates>
            </activity>`,
        searchViewArch: getEnrichedSearchArch(),
    });
    expect(".o_activity_view .o_activity_view_table").toHaveCount(1);
});

test("select all in the documents activity view reads the activity records", async () => {
    await mountView({
        type: "activity",
        resModel: "document.document",
        arch: `
            <activity string="Documents" js_class="documents_activity">
                <field name="folder_id"/>
                <templates>
                    <div t-name="activity-box">
                        <field name="name"/>
                    </div>
                </templates>
            </activity>`,
        searchViewArch: getEnrichedSearchArch(),
    });
    await press(["control", "a"]);
    await animationFrame();
    expect(".o_activity_view .o_activity_view_table").toHaveCount(1);
});

test("the documents activity view exposes no selection action menus", async () => {
    await mountView({
        type: "activity",
        resModel: "document.document",
        arch: `
            <activity string="Documents" js_class="documents_activity">
                <field name="folder_id"/>
                <templates>
                    <div t-name="activity-box">
                        <field name="name"/>
                    </div>
                </templates>
            </activity>`,
        searchViewArch: getEnrichedSearchArch(),
    });
    expect(getService("document.document").selectionActions.provider).toBe(null, {
        message: "it has no action menus: a preview must not read list/kanban ones",
    });
});

test("a documents reload refreshes the activity view once", async () => {
    onRpc("get_activity_data", () => {
        expect.step("get_activity_data");
    });
    await mountView({
        type: "activity",
        resModel: "document.document",
        arch: `
            <activity string="Documents" js_class="documents_activity">
                <field name="folder_id"/>
                <templates>
                    <div t-name="activity-box">
                        <field name="name"/>
                    </div>
                </templates>
            </activity>`,
        searchViewArch: getEnrichedSearchArch(),
    });
    expect.verifySteps(["get_activity_data"]);
    getService("document.document").reload();
    await animationFrame();
    await animationFrame();
    expect.verifySteps(["get_activity_data"]);
});
