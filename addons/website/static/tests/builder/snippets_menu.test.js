import { addBuilderOption } from "@html_builder/../tests/helpers";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { setContent } from "@html_editor/../tests/_helpers/selection";
import { insertText } from "@html_editor/../tests/_helpers/user_actions";
import { expect, test } from "@odoo/hoot";
import {
    animationFrame,
    click,
    Deferred,
    press,
    queryAllTexts,
    queryOne,
    waitFor,
} from "@odoo/hoot-dom";
import { onWillStart, xml } from "@odoo/owl";
import { contains, onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { WebsiteBuilderClientAction } from "@website/client_actions/website_preview/website_builder_action";

import {
    defineWebsiteModels,
    setupWebsiteBuilder,
    setupWebsiteBuilderWithSnippet,
} from "./website_helpers.js";

defineWebsiteModels();

test("open BuilderSidebar and discard", async () => {
    let websiteBuilder;
    patchWithCleanup(WebsiteBuilderClientAction.prototype, {
        setup() {
            websiteBuilder = this;
            super.setup();
        },
    });
    const { openBuilderSidebar } = await setupWebsiteBuilder(`<h1> Homepage </h1>`, {
        openEditor: false,
    });
    expect(".o_menu_systray .o-website-btn-custo-primary").toHaveCount(1);
    await openBuilderSidebar();
    expect(".o_menu_systray .o-website-btn-custo-primary").toHaveCount(0);
    await click(".o-snippets-top-actions button:contains(Discard)");
    await websiteBuilder.iframeLoaded;
    await animationFrame();
    await animationFrame();
    expect(".o_menu_systray .o-website-btn-custo-primary").toHaveCount(1);
});

test("navigate between builder tab don't fetch snippet description again", async () => {
    onRpc("render_public_asset", () => {
        expect.step("render_public_asset");
    });
    await setupWebsiteBuilder(`<h1> Homepage </h1>`);
    expect(queryAllTexts(".o-website-builder_sidebar .o-snippets-tabs button")).toEqual(
        ["Blocks", "Style", "Theme"],
    );
    expect(
        queryOne(".o-website-builder_sidebar .o-snippets-tabs button.active"),
    ).toHaveText("Blocks");
    expect.verifySteps(["render_public_asset"]);

    await contains(
        ".o-website-builder_sidebar .o-snippets-tabs button:contains(Theme)",
    ).click();
    await animationFrame();
    expect(
        queryOne(".o-website-builder_sidebar .o-snippets-tabs button.active"),
    ).toHaveText("Theme");

    await contains(
        ".o-website-builder_sidebar .o-snippets-tabs button:contains(Blocks)",
    ).click();
    expect(
        queryOne(".o-website-builder_sidebar .o-snippets-tabs button.active"),
    ).toHaveText("Blocks");
    expect.verifySteps([]);
});

test("undo and redo buttons", async () => {
    const { getEditor, getEditableContent, openBuilderSidebar } =
        await setupWebsiteBuilder("<p> Text </p>", {
            openEditor: false,
        });
    expect(".o_menu_systray .o-website-btn-custo-primary").toHaveCount(1);
    await openBuilderSidebar();
    expect(":iframe #wrap").not.toHaveClass("o_dirty");
    expect(":iframe #wrap").toHaveClass("o_editable");
    const editor = getEditor();
    const editableContent = getEditableContent();
    setContent(editableContent, "<p> Text[] </p>");
    await insertText(editor, "a");
    expect(editor.editable).toHaveInnerHTML(
        '<div id="wrap" class="oe_structure oe_empty o_editable o_dirty" data-oe-model="ir.ui.view" data-oe-id="539" data-oe-field="arch" data-editor-message-default="true" data-editor-message="DRAG BUILDING BLOCKS HERE" contenteditable="true"> <p> Texta </p> </div>',
    );
    await animationFrame();
    await click(".o-snippets-menu button.fa-undo");
    await animationFrame();
    expect(editor.editable).toHaveInnerHTML(
        '<div id="wrap" class="oe_structure oe_empty o_editable" data-oe-model="ir.ui.view" data-oe-id="539" data-oe-field="arch" data-editor-message-default="true" data-editor-message="DRAG BUILDING BLOCKS HERE" contenteditable="true"> <p> Text </p> </div>',
    );
    await click(".o-snippets-menu button.fa-arrow-rotate-right");
    expect(editor.editable).toHaveInnerHTML(
        '<div id="wrap" class="oe_structure oe_empty o_editable o_dirty" data-oe-model="ir.ui.view" data-oe-id="539" data-oe-field="arch" data-editor-message-default="true" data-editor-message="DRAG BUILDING BLOCKS HERE" contenteditable="true"> <p> Texta </p> </div>',
    );
});

test("activate customize tab without any selection", async () => {
    await setupWebsiteBuilder("<h1> Homepage </h1>");
    expect(
        queryOne(".o-website-builder_sidebar .o-snippets-tabs button.active"),
    ).toHaveText("Blocks");
    await contains(
        ".o-website-builder_sidebar .o-snippets-tabs button:contains(Style)",
    ).click();
    expect(
        queryOne(".o-website-builder_sidebar .o-snippets-tabs button.active"),
    ).toHaveText("Style");
});

test("Clicking on the 'Blocks' or 'Theme' tab should deactivate the options", async () => {
    await setupWebsiteBuilderWithSnippet("s_banner");

    await contains(":iframe .s_banner").click();
    await animationFrame();
    expect(".oe_overlay").toHaveCount(1);
    expect(".o-snippets-tabs button:contains('Style')").toHaveClass("active");
    expect(".o_customize_tab .options-container").toHaveCount(1);

    await contains(".o-snippets-tabs button:contains('Blocks')").click();
    expect(".oe_overlay").toHaveCount(0);
    await contains(".o-snippets-tabs button:contains('Style')").click();
    expect(".o-snippets-tabs button:contains('Style')").toHaveClass("active");
    expect(".o_customize_tab .options-container").toHaveCount(1);

    await contains(":iframe .s_banner").click();
    await waitFor(".o_customize_tab .options-container");
    expect(".oe_overlay").toHaveCount(1);
    expect(".o-snippets-tabs button:contains('Style')").toHaveClass("active");
    expect(".o_customize_tab .options-container").toHaveCount(1);

    await contains(".o-snippets-tabs button:contains('Theme')").click();
    expect(".oe_overlay").toHaveCount(0);
    await contains(".o-snippets-tabs button:contains('Style')").click();
    expect(".o-snippets-tabs button:contains('Style')").toHaveClass("active");
    expect(".o_customize_tab .options-container").toHaveCount(1);
});

test("Hotkeys on Theme and Blocks tab", async () => {
    await setupWebsiteBuilder("<section><p>TEST</p></section>");
    await waitFor(":iframe section");
    expect("[data-name=blocks]").toHaveClass("active");
    expect("[data-name=theme]").not.toHaveClass("active");
    await press(["alt", "2"]);
    await waitFor("[data-name=blocks]:not(.active)");
    expect("[data-name=theme]").toHaveClass("active");
    await press(["alt", "1"]);
    await waitFor("[data-name=theme]:not(.active)");
    expect("[data-name=blocks]").toHaveClass("active");
});

test("the options of the element left are blocked until the options of the element selected have loaded", async () => {
    const optionsLoaded = new Deferred();
    addBuilderOption(
        class extends BaseOptionComponent {
            static selector = ".target1";
            static template = xml`<BuilderButton classAction="'test'">Test 1</BuilderButton>`;
        },
    );
    addBuilderOption(
        class extends BaseOptionComponent {
            static selector = ".target2";
            static template = xml`<BuilderButton classAction="'test'">Test 2</BuilderButton>`;
            setup() {
                super.setup();
                onWillStart(() => optionsLoaded);
            }
        },
    );
    await setupWebsiteBuilder(`
        <div data-name="Target 1" class="target1">Homepage</div>
        <div data-name="Target 2" class="target2">Homepage2</div>
    `);
    await contains(":iframe .target1").click();
    expect(".o_customize_tab").not.toHaveClass("o_is_blocked");
    expect(".o_customize_tab").not.toHaveAttribute("inert");

    await contains(":iframe .target2").click();
    expect(".options-container").toHaveAttribute("data-container-title", "Target 1");
    expect(".o_customize_tab").toHaveClass("o_is_blocked");
    expect(".o_customize_tab").toHaveAttribute("inert");

    optionsLoaded.resolve();
    await animationFrame();
    expect(".options-container").toHaveAttribute("data-container-title", "Target 2");
    expect(".o_customize_tab").not.toHaveClass("o_is_blocked");
    expect(".o_customize_tab").not.toHaveAttribute("inert");
});
