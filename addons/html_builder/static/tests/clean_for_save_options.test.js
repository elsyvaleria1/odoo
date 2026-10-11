import { addBuilderOption, setupHTMLBuilder } from "@html_builder/../tests/helpers";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { describe, expect, test } from "@odoo/hoot";
import { xml } from "@odoo/owl";
import { contains, onRpc } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

test("clean for save of option with selector that matches an element on the page", async () => {
    onRpc("ir.ui.view", "save", ({ args }) => true);
    addBuilderOption(
        class extends BaseOptionComponent {
            static selector = ".test-options-target";
            static template = xml`
                    <BuilderButtonGroup>
                        <BuilderButton classAction="'x'"/>
                    </BuilderButtonGroup>
                `;
            static cleanForSave() {
                expect.step("clean for save option");
            }
        },
    );
    const { getEditor } = await setupHTMLBuilder(
        `<div class="test-options-target">a</div>`,
    );
    const editor = getEditor();
    await contains(":iframe .test-options-target").click();
    await contains("[data-class-action='x']").click();
    await editor.shared.savePlugin.save();
    expect.verifySteps(["clean for save option"]);
});

test("clean for save of option with selector and exclude that matches an element on the page", async () => {
    onRpc("ir.ui.view", "save", ({ args }) => true);
    addBuilderOption(
        class extends BaseOptionComponent {
            static selector = ".test-options-target";
            static template = xml`
                    <BuilderButtonGroup>
                        <BuilderButton classAction="'x'"/>
                    </BuilderButtonGroup>
                `;
            static exclude = "div";
            cleanForSave = (_) => {
                expect.step("clean for save option");
            };
        },
    );
    addBuilderOption(
        class extends BaseOptionComponent {
            static selector = ".test-options-target";
            static template = xml`
                    <BuilderButtonGroup>
                        <BuilderButton classAction="'y'"/>
                    </BuilderButtonGroup>
                `;
        },
    );
    const { getEditor } = await setupHTMLBuilder(
        `<div class="test-options-target">a</div>`,
    );
    const editor = getEditor();
    await contains(":iframe .test-options-target").click();
    await contains("[data-class-action='y']").click();
    await editor.shared.savePlugin.save();
    expect.verifySteps([]);
});
