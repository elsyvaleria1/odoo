// @ts-check

import { LiveFragments } from "@bus/public/live_fragments";
import { after, describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { startInteraction } from "@web/../tests/public/helpers";
import { mockService, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { browser } from "@web/core/browser/browser";
import { TAB_ID } from "@web/public/tab_id";

describe.current.tags("headless");

/** @param {number} quantity */
const lines = (quantity) =>
    `<ul data-fragment="cart.lines" data-fragment-live=""><li class="line">${quantity}</li></ul>`;

/**
 * Starts LiveFragments on `html` with a bus that hands its subscriber back.
 *
 * @param {string} html
 */
async function startWithBus(html) {
    /** @type {Function} */
    let subscriber = () => {};
    mockService("bus_service", {
        subscribe: (type, callback) => {
            if (type === "fragment.invalidated") {
                expect.step(`subscribe ${type}`);
                subscriber = callback;
            }
            return () => {};
        },
        unsubscribe: () => {},
        start: async () => {},
    });
    await startInteraction(LiveFragments, html);
    return (/** @type {any} */ notice) => subscriber(notice);
}

test("a page without live regions does not start the bus", async () => {
    await startWithBus(`<ul data-fragment="cart.lines"><li>1</li></ul>`);

    expect.verifySteps([]);
});

test("a notice from another tab replays its events and morphs the live regions", async () => {
    const notify = await startWithBus(`${lines(1)}<p data-fragment="other">old</p>`);
    expect.verifySteps(["subscribe fragment.invalidated"]);
    patchWithCleanup(browser, {
        fetch: async (url, init) => {
            expect.step(`fetch ${init.headers["X-Odoo-Partial-Navigation"]}`);
            return /** @type {Response} */ ({
                ok: true,
                text: async () =>
                    `<html><body>${lines(4)}<p data-fragment="other">new</p></body></html>`,
            });
        },
    });
    const listener = (ev) => expect.step(`event ${ev.detail.cart_quantity}`);
    document.addEventListener("website_sale:cart_updated", listener);
    after(() => document.removeEventListener("website_sale:cart_updated", listener));
    const line = document.querySelector(".line");

    await notify({
        keys: ["cart.lines", "other"],
        events: { "website_sale:cart_updated": { cart_quantity: 4 } },
        origin: "another-tab",
    });
    await animationFrame();

    expect.verifySteps(["event 4", "fetch cart.lines,other"]);
    expect(document.querySelector(".line")).toBe(line);
    expect(".line").toHaveText("4");
    expect("[data-fragment='other']").toHaveText("old");
});

test("a notice this tab caused is ignored", async () => {
    const notify = await startWithBus(lines(1));
    expect.verifySteps(["subscribe fragment.invalidated"]);
    patchWithCleanup(browser, {
        fetch: async () => {
            expect.step("fetch");
            return /** @type {Response} */ ({ ok: true, text: async () => "" });
        },
    });

    await notify({ keys: ["cart.lines"], events: {}, origin: TAB_ID });
    await animationFrame();

    expect.verifySteps([]);
});

test("a read answered after a newer one does not overwrite it", async () => {
    const notify = await startWithBus(lines(1));
    expect.verifySteps(["subscribe fragment.invalidated"]);
    /** @type {((html: string) => void)[]} */
    const answers = [];
    patchWithCleanup(browser, {
        fetch: () =>
            new Promise((resolve) =>
                answers.push((html) =>
                    resolve(
                        /** @type {Response} */ ({ ok: true, text: async () => html }),
                    ),
                ),
            ),
    });
    const notice = { keys: ["cart.lines"], events: {}, origin: "another-tab" };
    const older = notify(notice);
    const newer = notify(notice);
    answers[1](`<html><body>${lines(3)}</body></html>`);
    await newer;
    answers[0](`<html><body>${lines(2)}</body></html>`);
    await older;
    await animationFrame();

    expect(".line").toHaveText("3");
});

test("a newer read that fails leaves the older one's answer", async () => {
    const notify = await startWithBus(lines(1));
    expect.verifySteps(["subscribe fragment.invalidated"]);
    /** @type {((html: string | null) => void)[]} */
    const answers = [];
    patchWithCleanup(browser, {
        fetch: () =>
            new Promise((resolve) =>
                answers.push((html) =>
                    resolve(
                        /** @type {Response} */ ({
                            ok: html !== null,
                            text: async () => html,
                        }),
                    ),
                ),
            ),
    });
    const notice = { keys: ["cart.lines"], events: {}, origin: "another-tab" };
    const older = notify(notice);
    const newer = notify(notice);
    answers[1](null);
    await newer;
    answers[0](`<html><body>${lines(2)}</body></html>`);
    await older;
    await animationFrame();

    expect(".line").toHaveText("2");
});
