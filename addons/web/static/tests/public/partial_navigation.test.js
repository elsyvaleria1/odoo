// @ts-check

import { after, describe, expect, test } from "@odoo/hoot";
import { click, hover, queryAll, queryOne } from "@odoo/hoot-dom";
import { advanceTime, animationFrame } from "@odoo/hoot-mock";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { Offcanvas } from "@web/libs/bootstrap";
import { PartialNavigation, requestNavigation } from "@web/public/partial_navigation";

import { startInteraction } from "./helpers.js";

describe.current.tags("interaction_dev");

/** @param {string} rows */
const region = (rows) => `
    <div class="d-contents" data-fragment="portal.list" data-partial-navigation=".o_nav, .o_pager">
        <nav class="o_nav">
            <a class="o_sort" href="/my/orders?sortby=name">Sort by name</a>
            <a class="o_home" href="/my">Home</a>
            <form class="o_search" method="get" action="/my/orders">
                <input name="search" value="SO1"/>
                <button type="submit" name="search_in" value="name">Go</button>
            </form>
        </nav>
        <table><tbody>${rows}</tbody></table>
        <div class="o_pager"><a class="o_next" href="/my/orders/page/2">Next</a></div>
        <a class="o_record" href="#record">Record</a>
    </div>`;

/** @param {string} rows */
const page = (rows, title = "Orders") =>
    `<html><head><title>${title}</title></head><body><div id="wrapwrap">${region(rows)}</div></body></html>`;

/** @param {(url: string) => string | null} answer */
function serve(answer) {
    patchWithCleanup(browser, {
        fetch: async (url) => {
            const href = String(url);
            expect.step(`fetch ${new URL(href).pathname}${new URL(href).search}`);
            const html = answer(href);
            return /** @type {Response} */ ({
                ok: html !== null,
                url: href,
                text: async () => html || "",
            });
        },
    });
    patchWithCleanup(browser.history, {
        pushState: (state, _title, url) =>
            expect.step(
                `push ${state.partialNavigation} ${new URL(String(url)).pathname}`,
            ),
        replaceState: () => {},
    });
    patchWithCleanup(browser.location, {
        assign: (url) => expect.step(`assign ${new URL(String(url)).pathname}`),
    });
}

test("a link in scope swaps the region in place, pushes the URL and takes the title", async () => {
    await startInteraction(PartialNavigation, region("<tr><td>SO1</td></tr>"));
    serve(() => page("<tr><td>SO2</td></tr><tr><td>SO1</td></tr>", "Orders by name"));
    const table = queryOne("table");

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps(["fetch /my/orders?sortby=name", "push portal.list /my/orders"]);
    expect(queryOne("table")).toBe(table);
    expect("tbody tr").toHaveCount(2);
    expect(document.title).toBe("Orders by name");
});

test("the URL is pushed once the head is the next page's, and before the region swaps", async () => {
    await startInteraction(PartialNavigation, region("<tr><td>SO1</td></tr>"));
    serve(() =>
        page("<tr><td>SO2</td></tr><tr><td>SO1</td></tr>", "Orders by name").replace(
            "</title>",
            '</title><link rel="canonical" href="https://example.com/my/orders?sortby=name"/>',
        ),
    );
    after(() => document.head.querySelector('link[rel="canonical"]')?.remove());
    patchWithCleanup(browser.history, {
        pushState: () =>
            expect.step(
                `push under "${document.title}", ${document.head
                    .querySelector('link[rel="canonical"]')
                    ?.getAttribute("href")}, ${queryAll("tbody tr").length} row(s)`,
            ),
    });

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps([
        "fetch /my/orders?sortby=name",
        'push under "Orders by name", https://example.com/my/orders?sortby=name, 1 row(s)',
    ]);
    expect("tbody tr").toHaveCount(2);
});

test("a link outside the scopes navigates as usual", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page(""));

    await click(".o_record");
    await animationFrame();

    expect.verifySteps([]);
});

test("a link under data-no-partial-navigation navigates as usual, even in scope", async () => {
    await startInteraction(
        PartialNavigation,
        region("").replace(
            "</form>",
            '<div data-no-partial-navigation=""><a class="o_hit" href="#hit">SO7</a></div></form>',
        ),
    );
    serve(() => page(""));

    await click(".o_hit");
    await animationFrame();

    expect.verifySteps([]);
});

test("a Bootstrap toggle or an in-page anchor in scope is left to the browser", async () => {
    await startInteraction(
        PartialNavigation,
        region("").replace(
            "</nav>",
            '<div class="dropdown"><a class="o_toggle" href="/my/orders" data-bs-toggle="dropdown">Sort</a><div class="dropdown-menu"></div></div><a class="o_anchor" href="#top">Top</a></nav>',
        ),
    );
    serve(() => page(""));
    const preventDefault = (ev) => ev.preventDefault();
    document.addEventListener("click", preventDefault);
    after(() => document.removeEventListener("click", preventDefault));

    await click(".o_toggle");
    await click(".o_anchor");
    await animationFrame();

    expect.verifySteps([]);
});

test("an answer without the region falls back to a full navigation", async () => {
    await startInteraction(PartialNavigation, region("<tr><td>SO1</td></tr>"));
    serve(() => "<html><body><form class='o_login'></form></body></html>");

    await click(".o_next");
    await animationFrame();

    expect.verifySteps(["fetch /my/orders/page/2", "assign /my/orders/page/2"]);
    expect("tbody tr").toHaveCount(1);
});

test("a GET form in scope navigates with its fields and its submitter", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page("<tr><td>SO1</td></tr>"));

    await click(".o_search button");
    await animationFrame();

    expect.verifySteps([
        "fetch /my/orders?search=SO1&search_in=name",
        "push portal.list /my/orders",
    ]);
});

test("an interaction's o-navigate request is taken and marked as handled", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page(""));
    const request = new CustomEvent("o-navigate", {
        bubbles: true,
        cancelable: true,
        detail: { url: "/my/orders?search=SO3" },
    });

    const notTaken = queryOne(".o_search").dispatchEvent(request);
    await animationFrame();

    expect(notTaken).toBe(false);
    expect.verifySteps(["fetch /my/orders?search=SO3", "push portal.list /my/orders"]);
});

test("going back re-reads the page in place without pushing", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page("<tr><td>SO9</td></tr>"));

    window.dispatchEvent(
        new PopStateEvent("popstate", { state: { partialNavigation: "portal.list" } }),
    );
    await animationFrame();

    expect("tbody tr").toHaveCount(1);
    expect.verifySteps([
        `fetch ${new URL(browser.location.href).pathname}${new URL(browser.location.href).search}`,
    ]);
});

test("requestNavigation navigates in place from a scope, and as usual from anywhere else", async () => {
    await startInteraction(
        PartialNavigation,
        `${region("")}<p class="o_outside">out</p>`,
    );
    serve(() => page("<tr><td>SO4</td></tr>"));

    requestNavigation(queryOne(".o_search"), "/my/orders?search=SO4");
    await animationFrame();
    requestNavigation(queryOne(".o_outside"), "/my/orders?search=SO5");
    await animationFrame();

    expect.verifySteps([
        "fetch /my/orders?search=SO4",
        "push portal.list /my/orders",
        "assign /my/orders",
    ]);
});

test("the head follows the page: canonical, description and alternates are replaced", async () => {
    const head = (canonical, description) =>
        `<link rel="canonical" href="${canonical}"/><meta name="description" content="${description}"/>`;
    const stale = document
        .createRange()
        .createContextualFragment(head("https://shop.test/my/orders", "Your orders"));
    document.head.append(stale);
    after(() =>
        document.head
            .querySelectorAll('link[rel="canonical"], meta[name="description"]')
            .forEach((el) => el.remove()),
    );
    await startInteraction(PartialNavigation, region(""));
    serve(
        () =>
            `<html><head>${head("https://shop.test/my/orders?sortby=name", "Sorted")}</head><body>${region("")}</body></html>`,
    );

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps(["fetch /my/orders?sortby=name", "push portal.list /my/orders"]);
    expect(document.head.querySelectorAll('link[rel="canonical"]')).toHaveLength(1);
    expect(
        document.head.querySelector('link[rel="canonical"]').getAttribute("href"),
    ).toBe("https://shop.test/my/orders?sortby=name");
    expect(
        document.head.querySelector('meta[name="description"]').getAttribute("content"),
    ).toBe("Sorted");
});

test("window hears o-partial-navigation once the region is swapped", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page("<tr><td>SO7</td></tr>"));
    const listener = (ev) =>
        expect.step(
            `navigated ${ev.detail.key} ${document.querySelectorAll("tbody tr").length} ${ev.detail.page.querySelectorAll("tbody tr").length}`,
        );
    window.addEventListener("o-partial-navigation", listener);
    after(() => window.removeEventListener("o-partial-navigation", listener));

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps([
        "fetch /my/orders?sortby=name",
        "push portal.list /my/orders",
        "navigated portal.list 1 1",
    ]);
});

test("an open offcanvas in the region is hidden before navigating", async () => {
    await startInteraction(
        PartialNavigation,
        region("").replace(
            "</nav>",
            '</nav><div class="offcanvas show o_filters"></div>',
        ),
    );
    serve(() => page(""));
    patchWithCleanup(Offcanvas, {
        getInstance: (el) => ({ hide: () => expect.step(`hide ${el.className}`) }),
    });

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps([
        "hide offcanvas show o_filters",
        "fetch /my/orders?sortby=name",
        "push portal.list /my/orders",
    ]);
});

test("the region is aria-busy while the next page loads, and not once swapped in", async () => {
    await startInteraction(PartialNavigation, region(""));
    let release;
    patchWithCleanup(browser, {
        fetch: () =>
            new Promise((resolve) => {
                release = () =>
                    resolve(
                        /** @type {Response} */ ({
                            ok: true,
                            url: "http://localhost/my/orders?sortby=name",
                            text: async () => page("<tr><td>SO8</td></tr>"),
                        }),
                    );
            }),
    });
    patchWithCleanup(browser.history, { pushState: () => {} });

    await click(".o_sort");
    expect("[data-fragment='portal.list']").toHaveAttribute("aria-busy", "true");
    release();
    await animationFrame();

    expect("[data-fragment='portal.list']").not.toHaveAttribute("aria-busy");
    expect("tbody tr").toHaveCount(1);
});

test("a fetch that fails falls back to a full navigation", async () => {
    await startInteraction(PartialNavigation, region(""));
    patchWithCleanup(browser, {
        fetch: () => Promise.reject(new TypeError("Failed to fetch")),
    });
    patchWithCleanup(browser.location, {
        assign: (url) => expect.step(`assign ${new URL(String(url)).pathname}`),
    });

    await click(".o_next");
    await animationFrame();

    expect.verifySteps(["assign /my/orders/page/2"]);
});

test("<html> takes the next page's metadata: data attributes and lang", async () => {
    const html = document.documentElement;
    const before = { lang: html.getAttribute("lang"), main: html.dataset.mainObject };
    after(() => {
        html.setAttribute("lang", before.lang || "en");
        if (before.main === undefined) {
            delete html.dataset.mainObject;
        } else {
            html.dataset.mainObject = before.main;
        }
        delete html.dataset.staleMarker;
    });
    html.dataset.mainObject = "website.page(1,)";
    html.dataset.staleMarker = "1";
    await startInteraction(PartialNavigation, region(""));
    serve(
        () =>
            `<html lang="fr-FR" data-main-object="product.public.category(5,)"><head></head><body>${region("")}</body></html>`,
    );

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps(["fetch /my/orders?sortby=name", "push portal.list /my/orders"]);
    expect(html.getAttribute("lang")).toBe("fr-FR");
    expect(html.dataset.mainObject).toBe("product.public.category(5,)");
    expect(html.dataset.staleMarker).toBe(undefined);
});

test("requestNavigation runs the caller's fallback outside any scope", async () => {
    await startInteraction(
        PartialNavigation,
        `${region("")}<p class="o_outside">out</p>`,
    );
    serve(() => page(""));

    requestNavigation(queryOne(".o_outside"), "/somewhere", () =>
        expect.step("fallback"),
    );
    requestNavigation(queryOne(".o_search"), "/my/orders?search=SO6", () =>
        expect.step("fallback in scope"),
    );
    await animationFrame();

    expect.verifySteps([
        "fallback",
        "fetch /my/orders?search=SO6",
        "push portal.list /my/orders",
    ]);
});

/** @param {string} href */
const crumbs = (href) =>
    `<nav class="o_crumbs" data-fragment="t.crumbs" data-partial-navigation-oob=""><a href="${href}">Orders</a></nav>`;

test("out-of-band elements follow the page, paired by key and document order", async () => {
    await startInteraction(
        PartialNavigation,
        `${crumbs("/my/orders")}${region("")}${crumbs("/my/orders#footer")}`,
    );
    serve(
        () =>
            `<html><body>${crumbs("/my/orders?sortby=name")}${region("")}${crumbs("/my/orders?sortby=name#footer")}</body></html>`,
    );
    const [first, second] = queryAll(".o_crumbs");

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps(["fetch /my/orders?sortby=name", "push portal.list /my/orders"]);
    expect(queryAll(".o_crumbs")).toEqual([first, second]);
    expect(queryAll(".o_crumbs a").map((a) => a.getAttribute("href"))).toEqual([
        "/my/orders?sortby=name",
        "/my/orders?sortby=name#footer",
    ]);
});

test("an out-of-band element the next page lacks is hidden, and shown again", async () => {
    await startInteraction(PartialNavigation, `${crumbs("/my/orders")}${region("")}`);
    let withCrumbs = false;
    serve(
        () =>
            `<html><body>${withCrumbs ? crumbs("/my/orders?p=2") : ""}${region("")}</body></html>`,
    );

    await click(".o_sort");
    await animationFrame();
    expect(".o_crumbs").not.toBeVisible();

    withCrumbs = true;
    await click(".o_next");
    await animationFrame();
    expect(".o_crumbs").toBeVisible();
    expect(".o_crumbs a").toHaveAttribute("href", "/my/orders?p=2");
    expect.verifySteps([
        "fetch /my/orders?sortby=name",
        "push portal.list /my/orders",
        "fetch /my/orders/page/2",
        "push portal.list /my/orders/page/2",
    ]);
});

/**
 * @param {string} href
 * @param {string} [className]
 */
const langLink = (href, className = "") =>
    `<a class="o_lang ${className}" data-fragment="t.lang.fr" data-partial-navigation-oob="href" href="${href}">FR</a>`;

test("attribute out-of-band elements take only their listed attributes, every copy from the one counterpart", async () => {
    await startInteraction(
        PartialNavigation,
        `<header>${langLink("/fr/my/orders", "o_desktop")}</header>${region("")}<footer>${langLink("/fr/my/orders", "o_footer")}</footer>`,
    );
    serve(
        () =>
            `<html><body>${region("")}<div hidden="">${langLink("/fr/my/orders?sortby=name")}</div></body></html>`,
    );

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps(["fetch /my/orders?sortby=name", "push portal.list /my/orders"]);
    expect(
        queryAll(".o_lang").map((a) => [a.className, a.getAttribute("href")]),
    ).toEqual([
        ["o_lang o_desktop", "/fr/my/orders?sortby=name"],
        ["o_lang o_footer", "/fr/my/orders?sortby=name"],
    ]);
});

test("the fetch asks the server for the page without its header and footer", async () => {
    await startInteraction(PartialNavigation, region(""));
    patchWithCleanup(browser, {
        fetch: async (url, init) => {
            expect.step(`header ${init.headers["X-Odoo-Partial-Navigation"]}`);
            return /** @type {Response} */ ({
                ok: true,
                url: String(url),
                text: async () => page(""),
            });
        },
    });
    patchWithCleanup(browser.history, { pushState: () => {} });

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps(["header portal.list"]);
});

test("a mouse resting on a link preloads it, and the click uses the preload", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page("<tr><td>SO2</td></tr>"));

    await hover(".o_sort");
    await advanceTime(70);
    expect.verifySteps(["fetch /my/orders?sortby=name"]);

    await click(".o_sort");
    await animationFrame();

    expect.verifySteps(["push portal.list /my/orders"]);
    expect("tbody tr").toHaveCount(1);
});

test("a mouse passing over a link preloads nothing", async () => {
    await startInteraction(
        PartialNavigation,
        `${region("")}<p class="o_outside">out</p>`,
    );
    serve(() => page(""));

    await hover(".o_sort");
    await advanceTime(20);
    await hover(".o_outside");
    await advanceTime(100);

    expect.verifySteps([]);
});

test("a touch preloads at once, a focus after the delay", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page(""));

    queryOne(".o_sort").dispatchEvent(new TouchEvent("touchstart", { bubbles: true }));
    await animationFrame();
    expect.verifySteps(["fetch /my/orders?sortby=name"]);

    queryOne(".o_next").focus();
    await advanceTime(70);
    expect.verifySteps(["fetch /my/orders/page/2"]);
});

test("nothing is preloaded when the browser asks to save data", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page(""));
    patchWithCleanup(browser.navigator, { connection: { saveData: true } });

    await hover(".o_sort");
    await advanceTime(70);

    expect.verifySteps([]);
});

test("a preload past its 10 seconds is fetched again on click", async () => {
    let now = 1000;
    patchWithCleanup(Date, { now: () => now });
    await startInteraction(PartialNavigation, region(""));
    serve(() => page(""));

    await hover(".o_sort");
    await advanceTime(70);
    now += 10001;
    await click(".o_sort");
    await animationFrame();

    expect.verifySteps([
        "fetch /my/orders?sortby=name",
        "fetch /my/orders?sortby=name",
        "push portal.list /my/orders",
    ]);
});

test("a click before the hover delay fetches once", async () => {
    await startInteraction(PartialNavigation, region(""));
    serve(() => page(""));

    await hover(".o_sort");
    await click(".o_sort");
    await advanceTime(100);
    await animationFrame();

    expect.verifySteps(["fetch /my/orders?sortby=name", "push portal.list /my/orders"]);
});
