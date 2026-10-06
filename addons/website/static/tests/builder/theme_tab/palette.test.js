import { expect, test } from "@odoo/hoot";
import { Deferred } from "@odoo/hoot-dom";
import { contains, onRpc } from "@web/../tests/web_test_helpers";
import {
    defineWebsiteModels,
    onCustomizeTheme,
    setupWebsiteBuilder,
} from "@website/../tests/builder/website_helpers";

defineWebsiteModels();

test("theme tab: warning on palette change", async () => {
    onCustomizeTheme((groups) => {
        for (const [group, values] of Object.entries(groups)) {
            expect.step(`${group} ${JSON.stringify(values)}`);
        }
    });
    const def = new Deferred();
    onRpc("/website/theme_customize_bundle_reload", async (request) => {
        expect.step("asset reload");
        def.resolve();
        return "";
    });

    await setupWebsiteBuilder("", {
        styleContent: 'body { --has-customized-colors: "true"; }',
    });
    await contains(".o-snippets-tabs button[data-name=theme]").click();
    await contains(
        ".o_theme_tab [data-src='/website/static/src/img/snippets_options/palette.svg']",
    ).click();
    await contains(
        `[data-action-value="'default-light-1'"] .o-color-palette-pill span`,
    ).click();
    expect(".o_dialog").toHaveCount(1);
    await contains(".o_dialog .btn-secondary").click();
    expect(".o_dialog").toHaveCount(0);
    expect.verifySteps([]);
    await contains(
        ".o_theme_tab [data-src='/website/static/src/img/snippets_options/palette.svg']",
    ).click();
    await contains(
        `[data-action-value="'default-light-1'"] .o-color-palette-pill span`,
    ).click();
    expect(".o_dialog").toHaveCount(1);
    await contains(".o_dialog .btn-primary").click();
    await def;
    expect.verifySteps([
        `values {"color-palettes-name":"'default-light-1'"}`,
        "asset reload",
    ]);
});

test("theme tab: no warning on palette change", async () => {
    onCustomizeTheme((groups) => {
        for (const [group, values] of Object.entries(groups)) {
            expect.step(`${group} ${JSON.stringify(values)}`);
        }
    });
    const def = new Deferred();
    onRpc("/website/theme_customize_bundle_reload", async (request) => {
        expect.step("asset reload");
        def.resolve();
        return "";
    });

    await setupWebsiteBuilder("");
    await contains(".o-snippets-tabs button[data-name=theme]").click();
    await contains(
        ".o_theme_tab [data-src='/website/static/src/img/snippets_options/palette.svg']",
    ).click();
    await contains(
        `[data-action-value="'default-light-1'"] .o-color-palette-pill span`,
    ).click();
    await def;
    expect(".o_dialog").toHaveCount(0);
    expect.verifySteps([
        `values {"color-palettes-name":"'default-light-1'"}`,
        "asset reload",
    ]);
});
