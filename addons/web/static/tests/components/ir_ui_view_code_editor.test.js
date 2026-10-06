// @ts-check

import { before, expect, test } from "@odoo/hoot";
import { waitFor, waitForNone } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import {
    editAce,
    mountWithCleanup,
    preventResizeObserverError,
} from "@web/../tests/web_test_helpers";
import { loadAce } from "@web/core/lib/ace";
import { IrUiViewCodeEditor } from "@web/fields/specialized/ir_ui_view_ace/ir_ui_view_code_editor";
import { provideViewModel } from "@web/model/model";

before(() => loadAce());
preventResizeObserverError();

const ARCH = `<form>
    <field name="foo"/>
    <field name="bar"/>
</form>`;

/**
 * @param {Object} [params]
 * @param {string} [params.arch]
 * @param {Object[]} [params.invalidLocators]
 * @param {Object} [params.modelConfig]
 */
async function mountEditor({
    arch = ARCH,
    invalidLocators = [],
    modelConfig = { resModel: "ir.ui.view", resId: 1 },
} = {}) {
    class Parent extends Component {
        static components = { IrUiViewCodeEditor };
        static template = xml`
            <IrUiViewCodeEditor value="this.arch" mode="'xml'" maxLines="10" record="this.record"/>
        `;
        static props = null;
        props = useProps(this.constructor.props);
        setup() {
            provideViewModel(
                /** @type {any} */ (modelConfig && { config: modelConfig }),
            );
            this.arch = arch;
            this.record = { data: { invalid_locators: invalidLocators } };
        }
    }
    await mountWithCleanup(Parent);
}

test("highlights the node matching an invalid locator", async () => {
    await mountEditor({
        invalidLocators: [{ tag: "field", attrib: { name: "bar" }, sourceline: 3 }],
    });
    await waitFor(".invalid_locator");
    expect(".invalid_locator").toHaveCount(1);
});

test("no marker when the sourceline does not match", async () => {
    await mountEditor({
        invalidLocators: [{ tag: "field", attrib: { name: "bar" }, sourceline: 2 }],
    });
    await animationFrame();
    expect(".invalid_locator").toHaveCount(0);
});

test("broken_hierarchy locators are skipped", async () => {
    await mountEditor({
        invalidLocators: [
            {
                tag: "field",
                attrib: { name: "bar" },
                sourceline: 3,
                broken_hierarchy: true,
            },
        ],
    });
    await animationFrame();
    expect(".invalid_locator").toHaveCount(0);
});

test("attribute values with regex characters are matched literally", async () => {
    const arch = `<form>
    <field name="foo" domain="[('a', '=', 1)]"/>
</form>`;
    await mountEditor({
        arch,
        invalidLocators: [
            { tag: "field", attrib: { domain: "[('a', '=', 1)]" }, sourceline: 2 },
        ],
    });
    await waitFor(".invalid_locator");
    expect(".invalid_locator").toHaveCount(1);
});

test("no marker outside an ir.ui.view record model", async () => {
    await mountEditor({
        invalidLocators: [{ tag: "field", attrib: { name: "bar" }, sourceline: 3 }],
        modelConfig: { resModel: "other.model", resId: 1 },
    });
    await animationFrame();
    expect(".invalid_locator").toHaveCount(0);
});

test("editing clears the invalid locator markers", async () => {
    await mountEditor({
        invalidLocators: [{ tag: "field", attrib: { name: "bar" }, sourceline: 3 }],
    });
    await waitFor(".invalid_locator");

    await editAce("<form/>");
    await waitForNone(".invalid_locator");
    expect(".invalid_locator").toHaveCount(0);
});
