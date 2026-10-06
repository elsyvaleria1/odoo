import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts, queryOne } from "@odoo/hoot-dom";
import { animationFrame, runAllTimers } from "@odoo/hoot-mock";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { contains, mountWithCleanup, onRpc } from "@web/../tests/web_test_helpers";
import { XmlResourceEditor } from "@web_studio/client_action/xml_resource_editor/xml_resource_editor";

describe.current.tags("desktop");

defineMailModels();

test("can display warnings", async () => {
    onRpc("/web_studio/get_xml_editor_resources", async () => ({
        views: [
            {
                id: 1,
                arch: "<data/>",
            },
        ],
    }));

    class Parent extends Component {
        static components = { XmlResourceEditor };
        static template = xml`<XmlResourceEditor displayAlerts="this.props.state.displayAlerts" onClose="() => {}" mainResourceId="1" />`;
        static props = null;
        props = useProps(this.constructor.props);
    }

    const state = proxy({ displayAlerts: true });
    await mountWithCleanup(Parent, {
        props: { state },
    });
    await animationFrame();
    expect(".o_web_studio_code_editor_info .alert.alert-warning").toHaveCount(1);
    state.displayAlerts = false;
    await animationFrame();
    expect(".o_web_studio_code_editor_info .alert.alert-warning").toHaveCount(0);
});

test("stores and restores the cursor position when reloading resources after save", async () => {
    let arch = "<data>1\n2\n3\n4\n5\n</data>";
    onRpc("/web_studio/get_xml_editor_resources", () => {
        expect.step("load sources");
        return {
            views: [
                {
                    id: 1,
                    arch,
                },
            ],
        };
    });

    class Parent extends Component {
        static components = { XmlResourceEditor };
        static template = xml`<XmlResourceEditor onClose="() => {}" mainResourceId="1" reloadSources="this.state.key" onSave.bind="this.onSave" onCodeChange="() => {}"/>`;
        static props = null;
        props = useProps(this.constructor.props);

        setup() {
            this.state = proxy({ key: 0 });
        }
        async onSave({ newCode }) {
            await Promise.resolve();
            this.state.key++;
            arch = newCode;
        }
    }
    await mountWithCleanup(Parent);
    expect.verifySteps(["load sources"]);

    const aceEl = queryOne(".o_web_studio_code_editor.ace_editor");
    const editor = aceEl.env.editor;
    expect(editor.getCursorPosition()).toEqual({
        column: 0,
        row: 0,
    });
    editor.selection.moveToPosition({
        row: 3,
        column: 1,
    });
    editor.insert("appended");

    await contains(".o_web_studio_xml_resource_selector .btn-primary").click();
    await animationFrame();
    expect.verifySteps(["load sources"]);

    const newAceEl = queryOne(".o_web_studio_code_editor.ace_editor");
    const newEditor = newAceEl.env.editor;
    expect(aceEl).not.toBe(newAceEl);
    expect(editor).not.toBe(newEditor);

    expect(newEditor.getCursorPosition()).toEqual({
        column: 1,
        row: 3,
    });
});

test("the resource selector lists the main view with its inheriting and composed views under it", async () => {
    onRpc("/web_studio/get_xml_editor_resources", async () => ({
        main_view_key: 1,
        views: [
            {
                id: 1,
                name: "Main",
                xml_id: "m.main",
                key: "m.main",
                arch: "<data/>",
                called_xml_ids: ["m.called"],
            },
            {
                id: 2,
                name: "Child",
                xml_id: "m.child",
                key: "m.child",
                arch: "<data/>",
                inherit_id: [1, "Main"],
            },
            {
                id: 3,
                name: "Called",
                xml_id: "m.called",
                key: "m.called",
                arch: "<data/>",
            },
            {
                id: 4,
                name: "Grandchild",
                xml_id: "m.grand",
                key: "m.grand",
                arch: "<data/>",
                inherit_id: [2, "Child"],
            },
        ],
    }));
    class Parent extends Component {
        static components = { XmlResourceEditor };
        static template = xml`<XmlResourceEditor onClose="() => {}" mainResourceId="1"/>`;
        static props = null;
        props = useProps(this.constructor.props);
    }
    await mountWithCleanup(Parent);
    await animationFrame();
    await contains(
        ".o_web_studio_xml_resource_selector .o_select_menu_toggler",
    ).click();
    expect(queryAllTexts(".o_select_menu_item")).toEqual([
        "Main (m.main)",
        "Modified by:\nChild (m.child)",
        "Modified by:\nGrandchild (m.grand)",
        "Uses:\nCalled (m.called)",
    ]);

    await contains(".o_select_menu_input").edit("grand", { confirm: false });
    await runAllTimers();
    await animationFrame();
    expect(queryAllTexts(".o_select_menu_item")).toEqual([
        "Main (m.main)",
        "Modified by:\nChild (m.child)",
        "Modified by:\nGrandchild (m.grand)",
    ]);
});
