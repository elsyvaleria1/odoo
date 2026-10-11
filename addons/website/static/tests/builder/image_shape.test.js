import { Plugin } from "@html_editor/plugin";
import { describe, expect, test } from "@odoo/hoot";
import { queryFirst, setInputRange } from "@odoo/hoot-dom";
import { contains, onRpc } from "@web/../tests/web_test_helpers";

import { testGifImg, testImg } from "./image_test_helpers.js";
import {
    addPlugin,
    defineWebsiteModels,
    setupWebsiteBuilder,
} from "./website_helpers.js";

const THEME_COLOR_1 = "#0071E3";

defineWebsiteModels();

function decodeBase64(data) {
    return new TextDecoder("latin1").decode(Uint8Array.fromBase64(data));
}

function captureModifyImage(originalId) {
    const sent = {};
    onRpc(`/html_editor/modify_image/${originalId}`, async (request) => {
        Object.assign(sent, (await request.json()).params);
        expect.step("modify_image");
        return `/web/image/${originalId}-shaped/shaped.svg`;
    });
    onRpc("ir.ui.view", "save", () => true);
    return sent;
}

async function setShape(img, shapeId) {
    const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${img}
        </div>
    `);
    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();
    await contains("[data-label='Shape'] .dropdown").click();
    await contains(`[data-action-value='${shapeId}']`).click();
    await getEditor().shared.operation.next(() => {});
    return { getEditor, waitSidebarUpdated };
}

async function save() {
    await contains(".o-snippets-top-actions button:contains(Save)").click();
    await expect.waitForSteps(["modify_image"]);
}

describe("saving a shaped image", () => {
    test("sends the shape's parameters and its raster, never its SVG", async () => {
        const sent = captureModifyImage(1);
        const { getEditor, waitSidebarUpdated } = await setShape(
            testImg,
            "html_builder/geometric/geo_tetris",
        );
        await waitSidebarUpdated();
        await contains(`[data-action-id="flipImageShape"]:has(.oi-arrows-h)`).click();
        await getEditor().shared.operation.next(() => {});
        await save();

        expect(sent.mimetype).toBe(undefined);
        expect(sent.shape.id).toBe("html_builder/geometric/geo_tetris");
        expect(sent.shape.flip).toBe("x");
        expect(sent.shape.rotate).toBe(0);
        expect(sent.shape.animation_speed).toBe(0);
        expect(sent.shape.width).toBeGreaterThan(0);
        const raster = decodeBase64(sent.data);
        expect(raster.startsWith("RIFF")).toBe(true);
        expect(raster).not.toInclude("<svg");
    });

    test("sends a GIF as the raster of its shape", async () => {
        const sent = captureModifyImage(456);
        await setShape(testGifImg, "html_builder/geometric/geo_shuriken");
        await save();

        expect(sent.shape.id).toBe("html_builder/geometric/geo_shuriken");
        expect("flip" in sent.shape).toBe(false);
        expect(decodeBase64(sent.data).startsWith("GIF8")).toBe(true);
    });

    test("of an unprocessable original shows the original once unshaped", async () => {
        const { getEditor, waitSidebarUpdated } = await setShape(
            testGifImg,
            "html_builder/geometric/geo_shuriken",
        );
        await waitSidebarUpdated();
        await contains("[data-action-id='setImageShape']").click();
        await getEditor().shared.operation.next(() => {});

        expect(":iframe .test-options-target img").not.toHaveAttribute("data-shape");
        expect(":iframe .test-options-target img").toHaveAttribute(
            "src",
            "/website/static/src/img/snippets_options/header_effect_fade_out.gif",
        );
        expect(":iframe .test-options-target img").not.toHaveClass(
            "o_modified_image_to_save",
        );
    });

    test("sends the hover effect of a shaped image", async () => {
        const sent = captureModifyImage(1);
        const { waitSidebarUpdated } = await setupWebsiteBuilder(`
            <div class="test-options-target">
                ${testImg}
            </div>
        `);
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();
        await contains(
            ".options-container [data-label='Animation'] .dropdown-toggle",
        ).click();
        await contains(".o-dropdown--menu [data-action-value='onHover']").click();
        await waitSidebarUpdated();
        await save();

        expect(sent.shape.id).toBe("html_builder/geometric/geo_square");
        expect(sent.shape.hover_effect).toBe("overlay");
        expect(sent.shape.hover_effect_intensity).toBe(20);
        expect(decodeBase64(sent.data)).not.toInclude("<svg");
    });

    test("sends a hover color the server reads, whatever the browser computed", async () => {
        const sent = captureModifyImage(1);
        const { waitSidebarUpdated } = await setupWebsiteBuilder(`
            <div class="test-options-target">
                ${testImg}
            </div>
        `);
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();
        await contains(
            ".options-container [data-label='Animation'] .dropdown-toggle",
        ).click();
        await contains(".o-dropdown--menu [data-action-value='onHover']").click();
        await waitSidebarUpdated();
        queryFirst(":iframe .test-options-target img").dataset.hoverEffectColor =
            "color(srgb 1 0 0 / 0.5)";
        await save();

        expect(sent.shape.hover_effect_color).toBe("#FF000080");
    });
});

test("Should set a shape on an image", async () => {
    const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
    const editor = getEditor();
    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/geometric/geo_shuriken']").click();
    await editor.shared.operation.next(() => {});

    const img = queryFirst(":iframe .test-options-target img");
    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-attachment-id",
        "1",
    );
    expect(":iframe .test-options-target img").toHaveAttribute("data-original-id", "1");
    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-mimetype",
        "image/svg+xml",
    );
    expect(img.src.startsWith("data:image/svg+xml;base64,")).toBe(true);
    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-original-src",
        "/website/static/src/img/snippets_demo/s_text_image.webp",
    );
    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-mimetype-before-conversion",
        "image/webp",
    );
    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-shape",
        "html_builder/geometric/geo_shuriken",
    );
    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-file-name",
        "s_text_image.svg",
    );
    expect(":iframe .test-options-target img").not.toHaveAttribute("data-shape-colors");
});

test("Should set a shape on a GIF", async () => {
    const testGif = `<img
        src="/web/image/456-test/test.gif"
        class="img-fluid o_we_custom_image"
    >`;

    const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testGif}
        </div>
        `);
    const editor = getEditor();

    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/geometric/geo_shuriken']").click();
    await editor.shared.operation.next(() => {});

    const gif = queryFirst(":iframe .test-options-target img");

    expect(gif.src.startsWith("data:image/svg+xml;base64,")).toBe(true);

    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-mimetype",
        "image/svg+xml",
    );

    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-mimetype-before-conversion",
        "image/gif",
    );

    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-original-src",
        "/website/static/src/img/snippets_options/header_effect_fade_out.gif",
    );

    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-shape",
        "html_builder/geometric/geo_shuriken",
    );
});

test("Should change the shape color of an image", async () => {
    const { waitSidebarUpdated } = await setupWebsiteBuilder(
        `<div class="test-options-target">
            ${testImg}
        </div>`,
        {
            loadIframeBundles: true,
        },
    );
    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/pattern/pattern_wave_4']").click();
    await waitSidebarUpdated();

    expect(`[data-label="Colors"] .o_we_color_preview`).toHaveCount(4);

    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).toHaveStyle({
        backgroundColor: "rgb(0, 113, 227)",
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(2)`).toHaveStyle({
        backgroundColor: "rgb(240, 205, 168)",
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(3)`).toHaveStyle({
        backgroundColor: "rgb(246, 245, 244)",
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(4)`).toHaveStyle({
        backgroundColor: "rgb(27, 19, 25)",
    });

    expect(`:iframe .test-options-target img`).toHaveAttribute(
        "data-shape",
        "html_builder/pattern/pattern_wave_4",
    );
    expect(`:iframe .test-options-target img`).toHaveAttribute(
        "data-shape-colors",
        `${THEME_COLOR_1};#F0CDA8;#F6F5F4;;#1B1319`,
    );

    await contains(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).click();
    await contains(`.o_font_color_selector [data-color="#FF0000"]`).click();

    await waitSidebarUpdated();

    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).toHaveStyle({
        backgroundColor: "rgb(255, 0, 0)",
    });
    expect(`:iframe .test-options-target img`).toHaveAttribute(
        "data-shape-colors",
        "#FF0000;#F0CDA8;#F6F5F4;;#1B1319",
    );
});
test("Should change the shape color of an image with a class color", async () => {
    const { waitSidebarUpdated } = await setupWebsiteBuilder(
        `<div class="test-options-target">
            ${testImg}
        </div>`,
        {
            loadIframeBundles: true,
        },
    );
    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/pattern/pattern_wave_4']").click();
    await waitSidebarUpdated();

    expect(`[data-label="Colors"] .o_we_color_preview`).toHaveCount(4);

    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).toHaveStyle({
        backgroundColor: "rgb(0, 113, 227)",
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(2)`).toHaveStyle({
        backgroundColor: "rgb(240, 205, 168)",
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(3)`).toHaveStyle({
        backgroundColor: "rgb(246, 245, 244)",
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(4)`).toHaveStyle({
        backgroundColor: "rgb(27, 19, 25)",
    });

    expect(`:iframe .test-options-target img`).toHaveAttribute(
        "data-shape",
        "html_builder/pattern/pattern_wave_4",
    );
    expect(`:iframe .test-options-target img`).toHaveAttribute(
        "data-shape-colors",
        `${THEME_COLOR_1};#F0CDA8;#F6F5F4;;#1B1319`,
    );

    await contains(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).click();
    await contains(`.o_font_color_selector [data-color="o-color-2"]`).click();

    await waitSidebarUpdated();

    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).toHaveStyle({
        backgroundColor: "rgb(240, 205, 168)",
    });
    expect(`:iframe .test-options-target img`).toHaveAttribute(
        "data-shape-colors",
        "#F0CDA8;#F0CDA8;#F6F5F4;;#1B1319",
    );
});
test("Should not show transform action on shape that cannot bet transformed", async () => {
    const { waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/geometric/geo_shuriken']").click();
    await waitSidebarUpdated();
    expect(`[data-action-id="flipImageShape"]`).not.toHaveCount();
    expect(`[data-action-id="rotateImageShape"]`).not.toHaveCount();
});
describe("flip shape axis", () => {
    test("Should flip the shape X axis", async () => {
        const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        const editor = getEditor();
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/geometric/geo_tetris']",
        ).click();
        await waitSidebarUpdated();

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape",
            "html_builder/geometric/geo_tetris",
        );

        await contains(`[data-action-id="flipImageShape"]:has(.oi-arrows-h)`).click();
        await editor.shared.operation.next(() => {});

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape-flip",
            "x",
        );
    });
    test("Should unflip the shape X axis", async () => {
        const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        const editor = getEditor();
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/geometric/geo_tetris']",
        ).click();
        await waitSidebarUpdated();

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape",
            "html_builder/geometric/geo_tetris",
        );

        await contains(`[data-action-id="flipImageShape"]:has(.oi-arrows-h)`).click();
        await contains(`[data-action-id="flipImageShape"]:has(.oi-arrows-h)`).click();
        await editor.shared.operation.next(() => {});

        expect(`:iframe .test-options-target img`).not.toHaveAttribute(
            "data-shape-flip",
        );
    });
    test("Should flip the shape Y axis", async () => {
        const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        const editor = getEditor();
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/geometric/geo_tetris']",
        ).click();
        await waitSidebarUpdated();

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape",
            "html_builder/geometric/geo_tetris",
        );

        await contains(`[data-action-id="flipImageShape"]:has(.oi-arrows-v)`).click();
        await editor.shared.operation.next(() => {});

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape-flip",
            "y",
        );
    });
    test("Should flip the shape XY axis", async () => {
        const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        const editor = getEditor();
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/geometric/geo_tetris']",
        ).click();
        await waitSidebarUpdated();

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape",
            "html_builder/geometric/geo_tetris",
        );

        await contains(`[data-action-id="flipImageShape"]:has(.oi-arrows-h)`).click();
        await contains(`[data-action-id="flipImageShape"]:has(.oi-arrows-v)`).click();
        await editor.shared.operation.next(() => {});

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape-flip",
            "xy",
        );
    });
});
describe("rotate shape", () => {
    test("Should rotate the shape to the left", async () => {
        const { waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/geometric/geo_tetris']",
        ).click();
        await waitSidebarUpdated();

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape",
            "html_builder/geometric/geo_tetris",
        );

        await contains(
            `[data-action-id="rotateImageShape"]:has(.fa-rotate-left)`,
        ).click();
        await waitSidebarUpdated();
        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape-rotate",
            "270",
        );
    });
    test("Should remove rotate data when there is no rotation", async () => {
        const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        const editor = getEditor();
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/geometric/geo_tetris']",
        ).click();
        await waitSidebarUpdated();

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape",
            "html_builder/geometric/geo_tetris",
        );

        await contains(
            `[data-action-id="rotateImageShape"]:has(.fa-rotate-left)`,
        ).click();
        await contains(
            `[data-action-id="rotateImageShape"]:has(.fa-rotate-right)`,
        ).click();
        await editor.shared.operation.next(() => {});

        expect(`:iframe .test-options-target img`).not.toHaveAttribute(
            "data-shape-rotate",
        );
    });
    test("Should rotate the shape to the right", async () => {
        const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        const editor = getEditor();
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/geometric/geo_tetris']",
        ).click();
        await waitSidebarUpdated();

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape",
            "html_builder/geometric/geo_tetris",
        );

        await contains(
            `[data-action-id="rotateImageShape"]:has(.fa-rotate-right)`,
        ).click();
        await editor.shared.operation.next(() => {});

        expect(`:iframe .test-options-target img`).toHaveAttribute(
            "data-shape-rotate",
            "90",
        );
    });
});
test("Should not show animate speed if the shape is not animated", async () => {
    const { waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/geometric/geo_tetris']").click();
    await waitSidebarUpdated();
    expect(`[data-action-id="setImageShapeSpeed"]`).not.toHaveCount();
});
test("Should change the speed of an animated shape", async () => {
    const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
    const editor = getEditor();
    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/pattern/pattern_wave_4']").click();
    await waitSidebarUpdated();

    const originalSrc = queryFirst(":iframe .test-options-target img").src;

    await setInputRange(`[data-action-id="setImageShapeSpeed"] input`, 2);
    await editor.shared.operation.next(() => {});

    expect(`:iframe .test-options-target img`).toHaveAttribute(
        "data-shape-animation-speed",
        "2",
    );
    expect(`:iframe .test-options-target img`).not.toHaveAttribute("src", originalSrc);
});
describe("toggle ratio", () => {
    test("Should not be able to toggle the ratio of a pattern_wave_4", async () => {
        const { waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/pattern/pattern_wave_4']",
        ).click();
        await waitSidebarUpdated();

        expect(`[data-action-id="toggleImageShapeRatio"]`).not.toHaveCount();
    });
    test("A shape with togglable ratio should be added cropped and crop when clicked", async () => {
        const { waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
        await contains(":iframe .test-options-target img").click();
        await waitSidebarUpdated();

        await contains("[data-label='Shape'] .dropdown").click();
        await contains(
            "[data-action-value='html_builder/geometric/geo_shuriken']",
        ).click();
        await waitSidebarUpdated();
        const croppedSrc = queryFirst(":iframe .test-options-target img").src;

        await contains(`[data-action-id="toggleImageShapeRatio"] input`).click();
        await waitSidebarUpdated();
        expect(`:iframe .test-options-target img`).not.toHaveAttribute(
            "src",
            croppedSrc,
        );
    });
});

test("Should reset crop when removing shape with ratio", async () => {
    const { waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);

    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/geometric/geo_shuriken']").click();
    await waitSidebarUpdated();
    expect(`:iframe .test-options-target img`).toHaveAttribute("data-aspect-ratio");
    await contains("[data-action-id='setImageShape']").click();
    await waitSidebarUpdated();
    expect(`:iframe .test-options-target img`).not.toHaveAttribute("data-aspect-ratio");
});

test("Should have the correct active shape in the image shape selector", async () => {
    const { waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);

    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();
    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/geometric/geo_tetris']").click();
    await waitSidebarUpdated();
    await contains("[data-label='Shape'] .dropdown").click();
    expect("[data-action-value='html_builder/geometric/geo_tetris']").toHaveClass(
        "active",
    );
});

test("Should keep colors when changing speed and vice versa", async () => {
    const { getEditor, waitSidebarUpdated } = await setupWebsiteBuilder(
        `<div class="test-options-target">
            ${testImg}
        </div>`,
        {
            loadIframeBundles: true,
        },
    );
    const editor = getEditor();

    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();

    await contains("[data-label='Shape'] .dropdown").click();
    await contains("[data-action-value='html_builder/pattern/pattern_wave_4']").click();
    await waitSidebarUpdated();

    const imgSelector = ":iframe .test-options-target img";
    const initialColors = [
        queryFirst(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).style
            .backgroundColor,
        queryFirst(`[data-label="Colors"] .o_we_color_preview:nth-child(2)`).style
            .backgroundColor,
        queryFirst(`[data-label="Colors"] .o_we_color_preview:nth-child(3)`).style
            .backgroundColor,
        queryFirst(`[data-label="Colors"] .o_we_color_preview:nth-child(4)`).style
            .backgroundColor,
    ];

    await setInputRange(`[data-action-id="setImageShapeSpeed"] input`, -1);
    await editor.shared.operation.next(() => {});

    await contains(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).click();
    await contains(`.o_font_color_selector [data-color="#FF0000"]`).click();
    await waitSidebarUpdated();

    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).toHaveStyle({
        backgroundColor: "rgb(255, 0, 0)",
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(2)`).toHaveStyle({
        backgroundColor: initialColors[1],
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(3)`).toHaveStyle({
        backgroundColor: initialColors[2],
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(4)`).toHaveStyle({
        backgroundColor: initialColors[3],
    });

    expect(imgSelector).toHaveAttribute("data-shape-animation-speed", "-1");

    await setInputRange(`[data-action-id="setImageShapeSpeed"] input`, 2);
    await editor.shared.operation.next(() => {});

    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(1)`).toHaveStyle({
        backgroundColor: "rgb(255, 0, 0)",
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(2)`).toHaveStyle({
        backgroundColor: initialColors[1],
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(3)`).toHaveStyle({
        backgroundColor: initialColors[2],
    });
    expect(`[data-label="Colors"] .o_we_color_preview:nth-child(4)`).toHaveStyle({
        backgroundColor: initialColors[3],
    });

    expect(imgSelector).toHaveAttribute("data-shape-animation-speed", "2");
});

test("Be able to add and remove shape from custom groups", async () => {
    class CustomImageShapeGroupsPlugin extends Plugin {
        static id = "customImageShapeGroups";
        resources = {
            image_shape_groups_providers: (shapeGroups) => {
                const geometrics = shapeGroups.basic.subgroups.geometrics.shapes;
                const customShapes = {
                    "html_builder/geometric/geo_shuriken": {
                        ...geometrics["html_builder/geometric/geo_shuriken"],
                        selectLabel: "Custom Shuriken",
                    },
                    "html_builder/geometric/geo_diamond": {
                        ...geometrics["html_builder/geometric/geo_diamond"],
                        selectLabel: "Custom Diamond",
                    },
                };
                const extraShapes = {
                    "html_builder/geometric/geo_triangle": {
                        ...geometrics["html_builder/geometric/geo_triangle"],
                        selectLabel: "Extra Triangle",
                    },
                };
                delete geometrics["html_builder/geometric/geo_shuriken"];
                delete geometrics["html_builder/geometric/geo_diamond"];
                return {
                    basic: {
                        subgroups: {
                            custom: {
                                label: "Custom",
                                shapes: customShapes,
                            },
                        },
                    },
                    extra: {
                        label: "Extra",
                        subgroups: {
                            extra: {
                                label: "Extra",
                                shapes: extraShapes,
                            },
                        },
                    },
                };
            },
        };
    }
    addPlugin(CustomImageShapeGroupsPlugin);

    const { waitSidebarUpdated } = await setupWebsiteBuilder(`
        <div class="test-options-target">
            ${testImg}
        </div>
    `);
    await contains(":iframe .test-options-target img").click();
    await waitSidebarUpdated();
    await contains("[data-label='Shape'] .dropdown").click();
    expect(".o_pager_container").toHaveText(/Custom/);
    expect("button.o-hb-select-pager-tab[data-group-id='extra']").toHaveCount(1);
    expect("[data-action-value='html_builder/geometric/geo_shuriken']").toHaveCount(1);
    expect("[data-action-value='html_builder/geometric/geo_diamond']").toHaveCount(1);
    await contains("[data-action-value='html_builder/geometric/geo_shuriken']").click();
    await waitSidebarUpdated();
    expect(":iframe .test-options-target img").toHaveAttribute(
        "data-shape",
        "html_builder/geometric/geo_shuriken",
    );
    expect("div[data-label='Shape'] .dropdown").toHaveText("Custom Shuriken");
});
