import { describe, expect, test } from "@odoo/hoot";
import { click, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";

setupInteractionWhiteList(["portal.portal_search_panel", "web.partial_navigation"]);
describe.current.tags("interaction_dev");

const searchPanel = `
    <div id="o_portal_navbar_content">
        <form class="o_portal_search_panel">
            <div class="dropdown-menu">
                <a href="#name" class="dropdown-item active"><span>Name</span></a>
            </div>
            <input type="search" name="search" value="SO1"/>
            <button type="submit">Search</button>
        </form>
    </div>`;

function stubNavigation() {
    patchWithCleanup(browser, {
        fetch: async (url) => {
            expect.step(`fetch ${new URL(String(url)).search}`);
            return /** @type {Response} */ ({
                ok: true,
                url: String(url),
                text: async () =>
                    `<html><body><div data-fragment="portal.portal_layout">results</div></body></html>`,
            });
        },
    });
    patchWithCleanup(browser.history, { pushState: () => {}, replaceState: () => {} });
    patchWithCleanup(browser.location, {
        assign: (url) => expect.step(`assign ${new URL(String(url)).search}`),
    });
}

test("inside a partial navigation region, a search reads the results in place", async () => {
    await startInteractions(`
        <div class="d-contents" data-fragment="portal.portal_layout"
             data-partial-navigation="#o_portal_navbar_content, .o_portal_pager">
            ${searchPanel}
        </div>`);
    stubNavigation();

    await click(".o_portal_search_panel button");
    await animationFrame();

    expect.verifySteps(["fetch ?search_in=name&search=SO1"]);
    expect(queryOne("[data-fragment='portal.portal_layout']")).toHaveText("results");
});

test("without a region, a search navigates as before", async () => {
    await startInteractions(searchPanel);
    stubNavigation();

    await click(".o_portal_search_panel button");
    await animationFrame();

    expect.verifySteps(["assign ?search_in=name&search=SO1"]);
});
