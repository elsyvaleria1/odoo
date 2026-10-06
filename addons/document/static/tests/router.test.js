import "@document/core/router";

import { after, describe, expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { Component, t, useProps, xml } from "@odoo/owl";
import { mountWithCleanup, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";
import { redirect } from "@web/core/utils/urls";

describe.current.tags("desktop");

class Links extends Component {
    static props = { onClick: t.function() };
    props = useProps(this.constructor.props);
    static template = xml`
        <div class="o_links" t-on-click="this.props.onClick">
            <a class="o_token" href="/odoo/documents/aToken">document</a>
            <a class="o_action" href="/odoo/action-2">action</a>
        </div>`;
}

test("a documents token link still reaches its ancestors' click handlers", async () => {
    redirect("/odoo");
    // whatever else runs, this click must not navigate the test page away
    const guard = (ev) => ev.preventDefault();
    browser.addEventListener("click", guard, { capture: true });
    after(() => browser.removeEventListener("click", guard, { capture: true }));
    await mountWithCleanup(Links, {
        props: { onClick: () => expect.step("ancestor") },
    });

    await click(".o_token");
    expect.verifySteps(["ancestor"]);
});

test("a documents token link is left to the server, another app link is routed", async () => {
    redirect("/odoo");
    patchWithCleanup(router, {
        urlToState(url) {
            if (url.pathname !== "/odoo") {
                expect.step(`routed ${url.pathname}`);
            }
            return super.urlToState(url);
        },
    });
    await mountWithCleanup(Links, { props: { onClick: () => {} } });

    await click(".o_token");
    expect.verifySteps([]);
    expect(browser.location.pathname).toBe("/odoo/documents/aToken");

    redirect("/odoo");
    await click(".o_action");
    expect.verifySteps(["routed /odoo/action-2"]);
});

test("stateToUrl writes a token URL for the documents action only", () => {
    expect(router.stateToUrl({ action: "documents", access_token: "tok" })).toBe(
        "/odoo/documents/tok",
    );
    expect(
        router.stateToUrl({ action: "documents_portal", access_token: "tok" }),
    ).not.toBe("/odoo/documents/tok");
});
