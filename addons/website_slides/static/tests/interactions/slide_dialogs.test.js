import { describe, expect, getFixture, test } from "@odoo/hoot";
import { click, queryAll } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import {
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { Popover } from "@web/libs/bootstrap";
import { MainComponentsContainer } from "@web/ui/main_components_container";
import { CourseJoinBehavior } from "@website_slides/interactions/course_join";
import { syncEmptySectionFlags } from "@website_slides/js/public/slides_course_utils";

setupInteractionWhiteList([
    "website_slides.slide_upload",
    "website_slides.unsubscribe",
    "website_slides.embed_share",
]);
describe.current.tags("interaction_dev");

function mockUploadChoices() {
    onRpc("/slides/category/search_read", () => ({
        read_results: [{ id: 9, name: "Basics" }],
    }));
    onRpc("/slides/tag/search_read", () => ({ read_results: [] }));
}

test("an upload preset by the page opens once, not again when interactions restart", async () => {
    mockUploadChoices();
    const { core } = await startInteractions(`
        <a class="o_wslides_js_slide_upload" href="#" data-open-modal="article"
           data-channel-id="3" data-can-upload="True" data-can-publish="True">Add</a>`);
    await mountWithCleanup(MainComponentsContainer);
    await animationFrame();
    expect(".o_w_slide_upload_dialog_content").toHaveCount(1);
    expect(".o_wslides_js_slide_upload").not.toHaveAttribute("data-open-modal");

    core.stopInteractions();
    core.startInteractions();
    await animationFrame();
    expect(".o_w_slide_upload_dialog_content").toHaveCount(1);
});

test("a section preset by the page hides the section picker", async () => {
    mockUploadChoices();
    await startInteractions(`
        <a class="o_wslides_js_slide_upload" href="#" data-open-modal="article"
           data-channel-id="3" data-category-id="9" data-can-upload="True">Add</a>`);
    await mountWithCleanup(MainComponentsContainer);
    await animationFrame();

    expect(".o_w_slide_upload_dialog_content").toHaveCount(1);
    expect("label[for='category_id']").toHaveCount(0);
    expect("label[for='tag_ids']").toHaveCount(1);
});

test("without a preset section, the section picker is offered", async () => {
    mockUploadChoices();
    await startInteractions(`
        <a class="o_wslides_js_slide_upload" href="#" data-open-modal="article"
           data-channel-id="3" data-can-upload="True">Add</a>`);
    await mountWithCleanup(MainComponentsContainer);
    await animationFrame();

    expect("label[for='category_id']").toHaveCount(1);
});

test("the unsubscribe dialog receives typed props from the page's data attributes", async () => {
    await startInteractions(`
        <button class="o_wslides_js_channel_unsubscribe" data-channel-id="5"
            data-is-follower="True" data-enroll="public" data-visibility="public">Me</button>`);
    await mountWithCleanup(MainComponentsContainer);

    await click(".o_wslides_js_channel_unsubscribe");
    await animationFrame();
    expect(".modal").toHaveCount(1);
    expect(".modal input[type=checkbox]").toBeChecked();
});

test("a repeated join error replaces its popover instead of stacking one more", async () => {
    const cleanups = [];
    const el = document.createElement("div");
    el.textContent = "Join";
    getFixture().append(el);
    const join = new CourseJoinBehavior(
        {
            addListener: () => () => {},
            registerCleanup: (fn) => cleanups.push(fn),
        },
        el,
        { channel: { channelEnroll: "public", channelId: 1 } },
    );

    join._popoverAlert(el, "first");
    join._popoverAlert(el, "second");
    await animationFrame();
    expect(queryAll(".popover", { root: document.body })).toHaveLength(1);

    for (const cleanup of cleanups) {
        cleanup();
    }
    await animationFrame();
    expect(queryAll(".popover", { root: document.body })).toHaveLength(0);
});

test("copying an embed code twice keeps a single popover cleanup", async () => {
    patchWithCleanup(browser.navigator.clipboard, { writeText: async () => {} });
    let disposed = 0;
    patchWithCleanup(Popover.prototype, {
        dispose() {
            disposed++;
            return super.dispose(...arguments);
        },
    });
    const { core } = await startInteractions(`
        <div class="oe_slide_js_embed_code_widget">
            <textarea id="wslides_share_embed_id_4">&lt;iframe/&gt;</textarea>
            <button class="o_embed_clipboard_button" id="wslides_share_embed_button_id_4">Copy</button>
        </div>`);

    await click(".o_embed_clipboard_button");
    await animationFrame();
    await click(".o_embed_clipboard_button");
    await animationFrame();
    core.stopInteractions();

    expect(disposed).toBe(1);
});

test("empty-section flags follow the slides each section holds", () => {
    const root = document.createElement("div");
    root.innerHTML = `
        <li class="o_wslides_slide_list_category" data-id="a">
            <div class="o_wslides_slide_list_category_header">
                <div class="o_wslides_slides_list_drag"><span>A</span></div>
            </div>
        </li>
        <li class="o_wslides_slide_list_category" data-id="b">
            <div class="o_wslides_slide_list_category_header">
                <div class="o_wslides_slides_list_drag"><span>B</span><small>(empty)</small></div>
            </div>
            <ul><li class="o_wslides_slides_list_slide">slide</li></ul>
        </li>
        <li class="o_wslides_slide_list_category" data-id="c">
            <div class="o_wslides_slide_list_category_header"><span>no drag handle</span></div>
        </li>`;

    syncEmptySectionFlags(root);

    expect(root.querySelector("[data-id='a'] small")).toHaveText("(empty)");
    expect(root.querySelector("[data-id='b'] small")).toBe(null);
    expect(root.querySelector("[data-id='c'] small")).toBe(null);
});
