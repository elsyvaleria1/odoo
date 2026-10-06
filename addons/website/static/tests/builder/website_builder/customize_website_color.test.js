import { expect, test } from "@odoo/hoot";
import { animationFrame, Deferred } from "@odoo/hoot-dom";
import { xml } from "@odoo/owl";
import { contains, onRpc } from "@web/../tests/web_test_helpers";
import {
    addOption,
    defineWebsiteModels,
    onCustomizeTheme,
    setupWebsiteBuilder,
} from "@website/../tests/builder/website_helpers";

defineWebsiteModels();

test("BuilderColorPicker with action “customizeWebsiteColor” is correctly displayed", async () => {
    onCustomizeTheme((groups) => {
        for (const [group, values] of Object.entries(groups)) {
            expect.step(`${group} ${JSON.stringify(values)}`);
        }
    });

    let def = new Deferred();
    onRpc("/website/theme_customize_bundle_reload", async (request) => {
        expect.step("asset reload");
        def.resolve();
        return "";
    });
    addOption({
        selector: ".test-options-target",
        template: xml`
        <BuilderColorPicker
            enabledTabs="['theme', 'custom', 'gradient']"
            preview="false"
            defaultColor="''"
            action="'customizeWebsiteColor'"
            actionParam="{
                mainParam: 'test-custom',
                gradientColor: 'test-gradient',
                combinationColor: 'test',
                nullValue: 'NULL',
            }"
        />
        `,
    });
    await setupWebsiteBuilder(`<div class="test-options-target">b</div>`, {
        loadIframeBundles: true,
    });
    await contains(":iframe .test-options-target").click();
    await animationFrame();
    expect(".o-tab-content > .o_customize_tab").toHaveCount(1);

    expect.step("set preset");
    await contains("button.o_we_color_preview").click();
    await contains("button[data-color='o_cc4'").click();
    await def;
    expect.verifySteps([
        "set preset",
        'palette {"test-custom":"NULL","test":4}',
        'values {"test-gradient":"NULL"}',
        "asset reload",
    ]);

    def = new Deferred();
    expect.step("set solid color");
    await contains("button.o_we_color_preview").click();
    await contains("button.custom-tab").click();
    await contains("button[data-color='400']").click();
    await def;
    expect.verifySteps([
        "set solid color",
        'palette {"test-custom":"#CED4DA"}',
        'values {"test-gradient":"NULL"}',
        "asset reload",
    ]);

    def = new Deferred();
    expect.step("set preset on solid color");
    await contains("button.o_we_color_preview").click();
    await contains("button.theme-tab").click();
    await contains("button[data-color='o_cc3'").click();
    await def;
    expect.verifySteps([
        "set preset on solid color",
        'palette {"test-custom":"NULL","test":3}',
        'values {"test-gradient":"NULL"}',
        "asset reload",
    ]);

    def = new Deferred();
    expect.step("set gradient");
    await contains("button.o_we_color_preview").click();
    await contains("button.gradient-tab").click();
    await contains("button.o_gradient_color_button").click();
    await def;
    expect.verifySteps([
        "set gradient",
        'palette {"test-custom":"NULL"}',
        'values {"test-gradient":"linear-gradient(135deg, rgb(255, 204, 51) 0%, rgb(226, 51, 255) 100%)"}',
        "asset reload",
    ]);

    def = new Deferred();
    expect.step("set preset on gradient");
    await contains("button.o_we_color_preview").click();
    await contains("button.theme-tab").click();
    await contains("button[data-color='o_cc4'").click();
    await def;
    expect.verifySteps([
        "set preset on gradient",
        'palette {"test-custom":"NULL","test":4}',
        'values {"test-gradient":"NULL"}',
        "asset reload",
    ]);

    def = new Deferred();
    expect.step("reset");
    await contains("button.o_we_color_preview").click();
    await contains(".o_font_color_selector .fa-trash").click();
    await def;
    expect.verifySteps([
        "reset",
        'palette {"test-custom":"NULL","test":"NULL"}',
        'values {"test-gradient":"NULL"}',
        "asset reload",
    ]);

    await contains('.o-snippets-tabs button[data-name="theme"]').click();
    await contains('.o_theme_tab div[data-label="Color Presets"] button').click();
    await contains('div[id^="builder_collapse_content_"] button').click();
    await contains('div[data-label="Background"] .o_we_color_preview').click();
    await contains(".o-hb-colorpicker .custom-tab").click();
    await contains(".o_color_picker_inputs input.o_hex_input").edit("#77FF006E");
    await expect.waitForSteps([
        'palette {"o-cc1-bg":"#77FF00"}',
        'values {"o-cc1-bg-gradient":"null"}',
        "asset reload",
        'palette {"o-cc1-bg":"#77FF006E"}',
        'values {"o-cc1-bg-gradient":"null"}',
        "asset reload",
    ]);
    const colorPresetEl = document.querySelector(
        'div[id^="builder_collapse_content_"] .o_cc_preview_wrapper div',
    );
    const presetElStyles = window.getComputedStyle(colorPresetEl, "::before");
    expect(presetElStyles.backgroundImage).toInclude("transparent.png");
    expect(presetElStyles.backgroundSize.split(" ")[0]).toBe("32px");
});

test("a background edit reloads the bundle when its palette write compiles, though the gradient reset is a no-op", async () => {
    onCustomizeTheme((groups) => {
        expect.step(`customize_theme ${JSON.stringify(groups)}`);
        return { reload_bundles: "palette" in groups, theme_values_css: "" };
    });
    onRpc("/website/theme_customize_bundle_reload", () => {
        expect.step("asset reload");
        return {};
    });
    addOption({
        selector: ".test-options-target",
        template: xml`
        <BuilderColorPicker
            enabledTabs="['theme', 'custom', 'gradient']"
            preview="false"
            defaultColor="''"
            action="'customizeWebsiteColor'"
            actionParam="{ mainParam: 'o-cc1-bg', gradientColor: 'o-cc1-bg-gradient' }"
        />
        `,
    });
    await setupWebsiteBuilder(`<div class="test-options-target">b</div>`, {
        loadIframeBundles: true,
    });
    await contains(":iframe .test-options-target").click();
    await contains("button.o_we_color_preview").click();
    await contains("button.custom-tab").click();
    await contains("button[data-color='400']").click();
    await expect.waitForSteps([
        'customize_theme {"palette":{"o-cc1-bg":"#CED4DA"}}',
        'customize_theme {"values":{"o-cc1-bg-gradient":"null"}}',
        "asset reload",
    ]);
});
