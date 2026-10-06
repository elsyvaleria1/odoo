// @ts-check

import { describe, expect, globals, test } from "@odoo/hoot";
import { advanceTime } from "@odoo/hoot-mock";

describe.current.tags("headless");

/**
 * @type {Promise<{
 * extractSessionInfo: (html: string) => string | null,
 * getTextFromResponse: (response: Response) => Promise<string>,
 * isHashedAssetURL: (url: URL) => boolean,
 * isUniqueImageURL: (url: URL) => boolean,
 * restoreSessionInfo: (htmlBody: string, info: string) => string,
 * }> | null}
 */
let hooksPromise = null;
function loadServiceWorkerHooks() {
    hooksPromise ??= (async () => {
        const response = await globals.fetch("/web/static/src/service_worker.js");
        const source = await response.text();
        /** @type {any} */
        const fakeSelf = { addEventListener: () => {} };
        new Function("self", "caches", "fetch", source)(fakeSelf, undefined, undefined);
        expect(fakeSelf.__ODOO_SW_TEST_HOOKS__).not.toBe(undefined);
        return fakeSelf.__ODOO_SW_TEST_HOOKS__;
    })();
    return hooksPromise;
}

const url = (/** @type {string} */ path) => new URL(path, "https://example.com");

/**
 * @param {any} caches
 * @param {any} fetch
 * @param {any} [fakeSelf]
 */
async function loadServiceWorkerHooksWith(
    caches,
    fetch,
    fakeSelf = { addEventListener() {} },
) {
    const response = await globals.fetch("/web/static/src/service_worker.js");
    const source = await response.text();
    new Function("self", "caches", "fetch", source)(fakeSelf, caches, fetch);
    return fakeSelf.__ODOO_SW_TEST_HOOKS__;
}

describe("getTextFromResponse", () => {
    test("an empty response body reads as empty text", async () => {
        const { getTextFromResponse } = await loadServiceWorkerHooks();
        expect(
            await getTextFromResponse(new globals.Response(null, { status: 204 })),
        ).toBe("");
    });

    test("decodes UTF-8 across chunks and preserves the original response", async () => {
        const { getTextFromResponse } = await loadServiceWorkerHooks();
        const bytes = new TextEncoder().encode("a€b");
        const response = new globals.Response(
            new ReadableStream({
                start(controller) {
                    controller.enqueue(bytes.slice(0, 2));
                    controller.enqueue(bytes.slice(2));
                    controller.close();
                },
            }),
        );
        expect(await getTextFromResponse(response)).toBe("a€b");
        expect(await response.text()).toBe("a€b");
    });
});

test("message waiters are notified together and cleared for the next message", async () => {
    const listeners = new Map();
    const hooks = await loadServiceWorkerHooksWith(undefined, undefined, {
        addEventListener: (type, callback) => listeners.set(type, callback),
    });
    const first = hooks.waitingMessage("ready").then(() => expect.step("first"));
    const second = hooks.waitingMessage("ready").then(() => expect.step("second"));
    listeners.get("message")({ data: "unrelated" });
    await Promise.resolve();
    expect.verifySteps([]);
    listeners.get("message")({ data: "ready" });
    await Promise.all([first, second]);
    expect.verifySteps(["first", "second"]);
    const next = hooks.waitingMessage("ready").then(() => expect.step("next"));
    await Promise.resolve();
    expect.verifySteps([]);
    listeners.get("message")({ data: "ready" });
    await next;
    expect.verifySteps(["next"]);
});

test("a timed-out message waiter is dropped from the waiting list", async () => {
    const listeners = new Map();
    const hooks = await loadServiceWorkerHooksWith(undefined, undefined, {
        addEventListener: (type, callback) => listeners.set(type, callback),
    });
    const timedOut = hooks.waitingMessage("ready", 1000);
    const patient = hooks.waitingMessage("ready");
    expect(hooks.nextMessageMap.get("ready").size).toBe(2);
    await advanceTime(1000);
    expect(await timedOut).toBe(false);
    expect(hooks.nextMessageMap.get("ready").size).toBe(1);
    listeners.get("message")({ data: "ready" });
    expect(await patient).toBe(true);
    expect(hooks.nextMessageMap.has("ready")).toBe(false);
    const alone = hooks.waitingMessage("share", 1000);
    await advanceTime(1000);
    expect(await alone).toBe(false);
    expect(hooks.nextMessageMap.has("share")).toBe(false);
    const answered = hooks.waitingMessage("share", 1000);
    listeners.get("message")({ data: "share" });
    expect(await answered).toBe(true);
    await advanceTime(1000);
    expect(hooks.nextMessageMap.has("share")).toBe(false);
});

test("a share target that times out leaves no message waiter behind", async () => {
    /** @type {Map<any, any>[]} */
    const maps = [];
    /** @extends {Map<any, any>} */
    class SpyMap extends Map {
        /** @param {any} [entries] */
        constructor(entries) {
            super(entries);
            maps.push(this);
        }
    }
    const waiterCount = () =>
        maps.reduce(
            (count, map) =>
                count +
                [...map.values()].reduce(
                    (sum, value) =>
                        sum +
                        (value instanceof Set ? value.size : 0) +
                        (Array.isArray(value) ? value.length : 0),
                    0,
                ),
            0,
        );
    const listeners = new Map();
    const fakeSelf = {
        addEventListener: (/** @type {string} */ type, /** @type {any} */ callback) =>
            listeners.set(type, callback),
        clients: { get: async () => null },
    };
    const response = await globals.fetch("/web/static/src/service_worker.js");
    const source = await response.text();
    new Function("self", "caches", "fetch", "Map", source)(
        fakeSelf,
        undefined,
        undefined,
        SpyMap,
    );
    const shareTarget = () => {
        /** @type {Promise<any>[]} */
        const background = [];
        listeners.get("fetch")({
            request: {
                method: "POST",
                url: "https://example.com/odoo?share_target=1",
            },
            respondWith() {},
            waitUntil: (/** @type {Promise<any>} */ promise) =>
                background.push(promise),
        });
        return background[0];
    };
    for (let attempt = 0; attempt < 3; attempt++) {
        const handled = shareTarget();
        expect(waiterCount()).toBe(1);
        await advanceTime(30000);
        await handled;
        expect(waiterCount()).toBe(0);
    }
});

const BUNDLE_URL =
    "https://example.com/web/assets/esm/d3796119d3095207/web.assets_web.esm.js";

/**
 * @param {{ online?: boolean, kept?: Record<string, Response> }} [options]
 */
async function loadFetchHandler({ online = true, kept = {} } = {}) {
    const stored = new Map(Object.entries(kept));
    /** @type {string[]} */
    const fetched = [];
    let reachable = true;
    let status = 200;
    const cache = {
        match: async (/** @type {any} */ request) => stored.get(request.url ?? request),
        put: async (/** @type {any} */ request, /** @type {Response} */ response) => {
            stored.set(request.url ?? request, response);
        },
    };
    const fetch = async (/** @type {any} */ request) => {
        fetched.push(new URL(request.url ?? request).pathname);
        if (!reachable) {
            throw new TypeError("Failed to fetch");
        }
        return new Response("from the network", { status });
    };
    const listeners = new Map();
    await loadServiceWorkerHooksWith({ open: async () => cache }, fetch, {
        addEventListener: (/** @type {string} */ type, /** @type {any} */ callback) =>
            listeners.set(type, callback),
        navigator: { onLine: online },
    });
    /** @param {any} request */
    const dispatch = async (request) => {
        /** @type {Promise<any>[]} */
        const responses = [];
        /** @type {Promise<any>[]} */
        const background = [];
        listeners.get("fetch")({
            request,
            respondWith: (/** @type {Promise<any>} */ response) =>
                responses.push(Promise.resolve(response)),
            waitUntil: (/** @type {Promise<any>} */ promise) =>
                background.push(promise),
        });
        await Promise.all(background);
        return { answered: responses.length === 1, response: await responses[0] };
    };
    return {
        fetched,
        stored,
        asset: () => dispatch(new Request(BUNDLE_URL)),
        navigate: () =>
            dispatch({
                method: "GET",
                mode: "navigate",
                destination: "document",
                url: "https://example.com/odoo",
                headers: new Headers(),
            }).catch(() => ({ answered: true, response: undefined })),
        image: () =>
            dispatch(
                new Request(
                    "https://example.com/web/image/res.partner/7/image_128?unique=abc123",
                ),
            ),
        loseTheServer: () => {
            reachable = false;
        },
        findTheServer: () => {
            reachable = true;
        },
        answerWith: (/** @type {number} */ code) => {
            status = code;
        },
    };
}

describe("a hashed asset", () => {
    test("is left to the browser while the server answers, and kept on the side", async () => {
        const worker = await loadFetchHandler();
        expect((await worker.asset()).answered).toBe(false);
        expect(worker.fetched).toEqual([new URL(BUNDLE_URL).pathname]);
        expect(await worker.stored.get(BUNDLE_URL)?.text()).toBe("from the network");
    });

    test("is fetched for keeping once, not on every load", async () => {
        const worker = await loadFetchHandler();
        await worker.asset();
        await worker.asset();
        expect(worker.fetched).toHaveLength(1);
    });

    test("is answered from what was kept when the browser is offline", async () => {
        const worker = await loadFetchHandler({
            online: false,
            kept: { [BUNDLE_URL]: new Response("kept") },
        });
        const { answered, response } = await worker.asset();
        expect(answered).toBe(true);
        expect(await response.text()).toBe("kept");
        expect(worker.fetched).toEqual([]);
    });

    test("is answered from what was kept once a navigation found no server", async () => {
        const worker = await loadFetchHandler({
            kept: { [BUNDLE_URL]: new Response("kept") },
        });
        expect((await worker.asset()).answered).toBe(false);
        worker.loseTheServer();
        await worker.navigate();
        const { answered, response } = await worker.asset();
        expect(answered).toBe(true);
        expect(await response.text()).toBe("kept");
    });

    test("is left to the browser again once a navigation finds the server", async () => {
        const worker = await loadFetchHandler({
            kept: { [BUNDLE_URL]: new Response("kept") },
        });
        worker.loseTheServer();
        await worker.navigate();
        expect((await worker.asset()).answered).toBe(true);
        worker.findTheServer();
        await worker.navigate();
        expect((await worker.asset()).answered).toBe(false);
    });

    test("is answered from what was kept once any request of the worker found no server", async () => {
        const worker = await loadFetchHandler({
            kept: { [BUNDLE_URL]: new Response("kept") },
        });
        worker.loseTheServer();
        await worker.image();
        const { answered, response } = await worker.asset();
        expect(answered).toBe(true);
        expect(await response.text()).toBe("kept");
    });

    test("is not kept when the server answers an error", async () => {
        const worker = await loadFetchHandler();
        worker.answerWith(404);
        expect((await worker.asset()).answered).toBe(false);
        expect(worker.fetched).toHaveLength(1);
        expect(worker.stored.size).toBe(0);
    });

    test("offline with nothing kept answers an error response, not undefined", async () => {
        const worker = await loadFetchHandler({ online: false });
        worker.loseTheServer();
        const { answered, response } = await worker.asset();
        expect(answered).toBe(true);
        expect(response.type).toBe("error");
    });

    test("a failed fetch for keeping breaks nothing", async () => {
        const worker = await loadFetchHandler();
        worker.loseTheServer();
        expect((await worker.asset()).answered).toBe(false);
        expect(worker.stored.size).toBe(0);
    });
});

describe("staleWhileRevalidate", () => {
    test("a network failure with nothing cached answers an error response, not undefined", async () => {
        const caches = { open: async () => ({ match: async () => undefined }) };
        const fetch = () => Promise.reject(new TypeError("offline"));
        const hooks = await loadServiceWorkerHooksWith(caches, fetch);
        const request = new Request(
            "https://example.com/web/image/res.partner/7/image_128?unique=abc123",
        );
        const response = await hooks.staleWhileRevalidate({ request, waitUntil() {} });
        expect(response).not.toBe(undefined);
        expect(response.type).toBe("error");
    });

    test("a network failure with a cached copy answers the cached copy", async () => {
        const cached = new Response("cached");
        const caches = { open: async () => ({ match: async () => cached }) };
        const fetch = () => Promise.reject(new TypeError("offline"));
        const hooks = await loadServiceWorkerHooksWith(caches, fetch);
        const request = new Request(
            "https://example.com/web/image/res.partner/7/image_128?unique=abc123",
        );
        const response = await hooks.staleWhileRevalidate({ request, waitUntil() {} });
        expect(response).toBe(cached);
    });
});

describe("extractSessionInfo", () => {
    test("extracts a simple session info object", async () => {
        const { extractSessionInfo } = await loadServiceWorkerHooks();
        const html = `<html><script>odoo.__session_info__ = {"db":"x","uid":7};</script></html>`;
        expect(extractSessionInfo(html)).toBe(`{"db":"x","uid":7}`);
    });

    test("survives a '};'-containing string value", async () => {
        const { extractSessionInfo } = await loadServiceWorkerHooks();
        const info = `{"db":"x","user":"a};b","uid":7}`;
        const html = `<script>odoo.__session_info__ = ${info};</script>`;
        expect(extractSessionInfo(html)).toBe(info);
    });

    test("handles escaped quotes and nested objects", async () => {
        const { extractSessionInfo } = await loadServiceWorkerHooks();
        const info = `{"company":"ACME \\"};\\" Inc","ctx":{"lang":"en_US","nested":{"a":"}"}}}`;
        const html = `odoo.__session_info__ = ${info};\nodoo.other = 1;`;
        expect(extractSessionInfo(html)).toBe(info);
    });

    test("returns null when absent or malformed", async () => {
        const { extractSessionInfo } = await loadServiceWorkerHooks();
        expect(extractSessionInfo("<html>no session</html>")).toBe(null);
        expect(extractSessionInfo("odoo.__session_info__ = null;")).toBe(null);
        expect(extractSessionInfo(`odoo.__session_info__ = {"a":1`)).toBe(null);
    });
});

describe("restoreSessionInfo", () => {
    test("splices info back into the placeholder", async () => {
        const { restoreSessionInfo } = await loadServiceWorkerHooks();
        const info = `{"db":"x","uid":7}`;
        const shell = `<script>odoo.__session_info__ = @@@session_info_secret@@@;</script>`;
        expect(restoreSessionInfo(shell, info)).toBe(
            `<script>odoo.__session_info__ = ${info};</script>`,
        );
    });

    test("preserves `$`-substitution sequences in the session info", async () => {
        const { restoreSessionInfo } = await loadServiceWorkerHooks();
        const info = `{"name":"ACME $' $& $$ $\` $1 Corp"}`;
        const shell = `odoo.__session_info__ = @@@session_info_secret@@@;`;
        expect(restoreSessionInfo(shell, info)).toBe(
            `odoo.__session_info__ = ${info};`,
        );
    });
});

describe("isHashedAssetURL", () => {
    test("content-hashed asset bundles match", async () => {
        const { isHashedAssetURL } = await loadServiceWorkerHooks();
        expect(
            isHashedAssetURL(url("/web/assets/d3796119d3095207/web.assets_web.min.js")),
        ).toBe(true);
        expect(
            isHashedAssetURL(
                url("/web/assets/esm/d3796119d3095207/web.assets_web.esm.js"),
            ),
        ).toBe(true);
    });

    test("mutable asset URLs (debug/any/%) do not", async () => {
        const { isHashedAssetURL } = await loadServiceWorkerHooks();
        expect(isHashedAssetURL(url("/web/assets/debug/web.assets_web.min.js"))).toBe(
            false,
        );
        expect(isHashedAssetURL(url("/web/assets/any/web.assets_web.min.js"))).toBe(
            false,
        );
        expect(isHashedAssetURL(url("/web/assets/%/web.assets_web.min.js"))).toBe(
            false,
        );
        expect(isHashedAssetURL(url("/web/assets"))).toBe(false);
    });

    test("unrelated paths never match", async () => {
        const { isHashedAssetURL } = await loadServiceWorkerHooks();
        expect(isHashedAssetURL(url("/web/assetsfoo/1"))).toBe(false);
        expect(isHashedAssetURL(url("/odoo/some-action"))).toBe(false);
        expect(isHashedAssetURL(url("/web/dataset/call_kw"))).toBe(false);
        expect(
            isHashedAssetURL(url("/web/image/res.partner/7/image_128?unique=abc123")),
        ).toBe(false);
    });
});

describe("isUniqueImageURL", () => {
    test("images require a cache-busting unique= token", async () => {
        const { isUniqueImageURL } = await loadServiceWorkerHooks();
        expect(isUniqueImageURL(url("/web/image/res.partner/7/image_128"))).toBe(false);
        expect(
            isUniqueImageURL(url("/web/image/res.partner/7/image_128?unique=abc123")),
        ).toBe(true);
        expect(
            isUniqueImageURL(url("/web/image/res.partner/7/image_128?unique=")),
        ).toBe(false);
    });

    test("translations are NOT served stale", async () => {
        const { isUniqueImageURL } = await loadServiceWorkerHooks();
        expect(isUniqueImageURL(url("/web/webclient/translations"))).toBe(false);
        expect(
            isUniqueImageURL(url("/web/webclient/translations?hash=abc123&lang=fr_FR")),
        ).toBe(false);
        expect(isUniqueImageURL(url("/web/webclient/translations/abc123"))).toBe(false);
    });

    test("unrelated paths never match", async () => {
        const { isUniqueImageURL } = await loadServiceWorkerHooks();
        expect(isUniqueImageURL(url("/web/imagefoo/1?unique=x"))).toBe(false);
        expect(
            isUniqueImageURL(url("/web/assets/d3796119d3095207/web.assets_web.min.js")),
        ).toBe(false);
        expect(isUniqueImageURL(url("/odoo/some-action"))).toBe(false);
        expect(isUniqueImageURL(url("/web/dataset/call_kw"))).toBe(false);
    });
});
