import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, click } from "@odoo/hoot-dom";
import {
    mockSendRequests,
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

setupInteractionWhiteList(["website.post_link", "web.partial_navigation"]);

describe.current.tags("interaction_dev");

test("post_link adds and removes class on setup/destroy", async () => {
    const { core } = await startInteractions(`
        <div id="wrapwrap">
            <span data-post="/some/url" class="post_link">All</span>
        </div>
    `);
    expect(core.interactions).toHaveLength(1);
    expect("span").toHaveClass("o_post_link_js_loaded");
    core.stopInteractions();
    expect(core.interactions).toHaveLength(0);
    expect("span").not.toHaveClass("o_post_link_js_loaded");
});

test("post_link handle clicks by sending a request", async () => {
    const requests = mockSendRequests();
    await startInteractions(`
        <div id="wrapwrap">
            <span data-post="/some/url" class="post_link">All</span>
        </div>
    `);
    expect(requests).toEqual([]);
    click("span");
    await animationFrame();
    expect(requests).toEqual([{ url: "/some/url", method: "POST" }]);
});

test("post_link with nothing to post navigates in place inside a partial navigation scope", async () => {
    const requests = mockSendRequests();
    await startInteractions(`
        <div id="wrapwrap">
            <div data-fragment="events" data-partial-navigation=".filters">
                <div class="filters"><span data-post="/event/tags/x?prevent_redirect=True" class="post_link">Tag X</span></div>
                <p class="o_list">all events</p>
            </div>
        </div>
    `);
    patchWithCleanup(browser, {
        fetch: async (url) => {
            expect.step(`fetch ${new URL(String(url)).pathname}`);
            return /** @type {Response} */ ({
                ok: true,
                url: String(url),
                text: async () =>
                    `<html><body><div data-fragment="events"><p class="o_list">tag X events</p></div></body></html>`,
            });
        },
    });
    patchWithCleanup(browser.history, { pushState: () => {}, replaceState: () => {} });

    click("span");
    await animationFrame();

    expect.verifySteps(["fetch /event/tags/x"]);
    expect(requests).toEqual([]);
    expect(".o_list").toHaveText("tag X events");
});

test("post_link outside any scope, or with data to post, still posts", async () => {
    const requests = mockSendRequests();
    await startInteractions(`
        <div id="wrapwrap">
            <div data-fragment="events" data-partial-navigation=".filters">
                <div class="filters"><span data-post="/with/data" data-post_mode="x" class="post_link o_with_data">A</span></div>
            </div>
            <span data-post="/outside" class="post_link o_outside">B</span>
        </div>
    `);

    click(".o_with_data");
    await animationFrame();
    click(".o_outside");
    await animationFrame();

    expect(requests).toEqual([
        { url: "/with/data", method: "POST" },
        { url: "/outside", method: "POST" },
    ]);
});
