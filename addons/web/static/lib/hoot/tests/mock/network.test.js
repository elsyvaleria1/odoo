/** @odoo-module */

import { after, describe, expect, mockFetch, test } from "@odoo/hoot";

import { mockHistory, mockLocation, mockNavigation } from "../../mock/network.js";
import { parseUrl } from "../local_helpers.js";

/**
 * @param {EventTarget} target
 * @param {string} type
 * @param {(ev: any) => any} listener
 */
function listen(target, type, listener) {
    target.addEventListener(type, listener);
    after(() => target.removeEventListener(type, listener));
}

/** @param {Blob | MediaSource} obj */
function createObjectURL(obj) {
    const url = URL.createObjectURL(obj);
    after(() => URL.revokeObjectURL(url));
    return url;
}

describe(parseUrl(import.meta.url), () => {
    test("setup network values", async () => {
        expect(document.cookie).toBe("");

        document.cookie = "cids=4";
        document.title = "kek";

        expect(document.cookie).toBe("cids=4");
        expect(document.title).toBe("kek");
    });

    test("values are reset between test", async () => {
        expect(document.cookie).toBe("");
        expect(document.title).toBe("");
    });

    test("fetch with internal URLs works without mocking fetch", async () => {
        const blob = new Blob([JSON.stringify({ name: "coucou" })], {
            type: "application/json",
        });
        const blobUrl = createObjectURL(blob);
        const blobResponse = await fetch(blobUrl).then((res) => res.json());
        const dataResponse = await fetch("data:text/html,<body></body>").then((res) =>
            res.text(),
        );

        expect(blobResponse).toEqual({ name: "coucou" });
        expect(dataResponse).toBe("<body></body>");

        await expect(fetch("http://some.url")).rejects.toThrow(/fetch is not mocked/);
    });

    test("fetch with internal URLs should return default value", async () => {
        mockFetch(expect.step);

        const external = await fetch("http://some.url").then((res) => res.text());
        const internal = await fetch("/odoo").then((res) => res.text());
        const data = await fetch("data:text/html,<body></body>").then((res) =>
            res.text(),
        );

        expect(external).toBe("null");
        expect(internal).toBe("null");
        expect(data).toBe("<body></body>");

        expect.verifySteps([
            "http://some.url",
            "/odoo",
            "data:text/html,<body></body>",
        ]);
    });

    test("fetch JSON with blob URLs", async () => {
        mockFetch(expect.step);

        const blob = new Blob([JSON.stringify({ name: "coucou" })], {
            type: "application/json",
        });
        const blobUrl = createObjectURL(blob);
        const response = await fetch(blobUrl);
        const json = await response.json();

        expect(json).toEqual({ name: "coucou" });

        expect.verifySteps([blobUrl]);
    });

    test("fetch with mocked blob URLs", async () => {
        mockFetch((input) => {
            expect.step(input);
            return "Some other content";
        });

        const blob = new Blob([JSON.stringify({ name: "coucou" })], {
            type: "application/json",
        });
        const blobUrl = createObjectURL(blob);
        const response = await fetch(blobUrl);

        expect(response.headers).toEqual(new Headers([["Content-Type", "text/plain"]]));

        const text = await response.text();

        expect(text).toBe("Some other content");

        expect.verifySteps([blobUrl]);
    });

    test("response readers decode a blob body and preserve clone isolation", async () => {
        const response = new Response(
            new Blob(['{"value":', "42}"], { type: "application/json" }),
        );
        const clone = response.clone();
        expect(await response.json()).toEqual({ value: 42 });
        expect(response.bodyUsed).toBe(true);
        expect(clone.bodyUsed).toBe(false);
        expect(await clone.text()).toBe('{"value":42}');
        await expect(response.text()).rejects.toThrow(/already read/);
    });

    test("mock response with nested blobs", async () => {
        mockFetch(
            () =>
                new Blob([
                    "some blob",
                    new Blob([" with nested content"], { type: "text/plain" }),
                ]),
        );

        const response = await fetch("/nestedBlob");
        const blob = await response.blob();
        const result = await blob.text();

        expect(result).toBe("some blob with nested content");
    });

    test("mock responses: array buffer", async () => {
        mockFetch(() => "some text");

        const response = await fetch("/arrayBuffer");
        const result = await response.arrayBuffer();

        expect(result).toBeInstanceOf(ArrayBuffer);
        expect(new TextDecoder("utf-8").decode(result)).toBe("some text");
    });

    test("mock responses: blob", async () => {
        mockFetch(() => "blob content");

        const response = await fetch("/blob");
        const result = await response.blob();

        expect(result).toBeInstanceOf(Blob);
        expect(result.size).toBe(12);

        const buffer = await result.arrayBuffer();
        expect(new TextDecoder("utf-8").decode(buffer)).toBe("blob content");
    });

    test("mock responses: bytes", async () => {
        mockFetch(() => "some text");

        const response = await fetch("/bytes");
        const result = await response.bytes();

        expect(result).toBeInstanceOf(Uint8Array);
        expect(new TextDecoder("utf-8").decode(result)).toBe("some text");
    });

    test("mock responses: formData", async () => {
        mockFetch(() => {
            const data = new FormData();
            data.append("name", "Frodo");
            return data;
        });

        const response = await fetch("/formData");
        const result = await response.formData();

        expect(result).toBeInstanceOf(FormData);
        expect(result.get("name")).toBe("Frodo");
    });

    test("mock responses: json", async () => {
        mockFetch(() => ({ json: "content" }));

        const response = await fetch("/json");
        const result = await response.json();

        expect(result).toEqual({ json: "content" });
    });

    test("mock responses: text", async () => {
        mockFetch(() => "some text");

        const response = await fetch("/text");
        const result = await response.text();

        expect(result).toBe("some text");
    });

    test("mock responses: a binary body reads as its bytes, and as UTF-8 text", async () => {
        const text = "ünïcödé ✓";
        const encoded = new TextEncoder().encode(text);
        mockFetch(() => new Response(encoded));

        expect(await (await fetch("/text")).text()).toBe(text);
        expect([...(await (await fetch("/bytes")).bytes())]).toEqual([...encoded]);
    });

    test("mock responses: bytes that are not UTF-8 survive byte readers", async () => {
        const backing = new Uint8Array([0x01, 0xff, 0x00, 0xfe, 0x02]);
        mockFetch(() => new Response(backing.subarray(1, 4)));

        expect([...(await (await fetch("/bytes")).bytes())]).toEqual([
            0xff, 0x00, 0xfe,
        ]);
        const buffer = await (await fetch("/arrayBuffer")).arrayBuffer();
        expect([...new Uint8Array(buffer)]).toEqual([0xff, 0x00, 0xfe]);
    });

    test("mock blobs: binary parts keep their bytes", async () => {
        const blob = new Blob([new Uint8Array([0xff, 0x00]), "ok"]);

        expect([...(await blob.bytes())]).toEqual([0xff, 0x00, 0x6f, 0x6b]);
    });

    test("navigation: history.pushState is a same-document push the navigate event sees", async () => {
        const seen = [];
        listen(mockNavigation, "navigate", (ev) =>
            seen.push([
                ev.navigationType,
                ev.destination.sameDocument,
                ev.userInitiated,
            ]),
        );
        const before = mockHistory.length;
        mockHistory.pushState({ a: 1 }, "", "/somewhere");

        expect(seen).toEqual([["push", true, false]]);
        expect(mockLocation.pathname).toBe("/somewhere");
        expect(mockHistory.state).toEqual({ a: 1 });
        expect(mockHistory.length).toBe(before + 1);
        expect(mockNavigation.currentEntry.url).toBe(mockLocation.href);
    });

    test("navigation: history.back traverses, then fires popstate with the entry's state", async () => {
        const steps = [];
        mockHistory.pushState({ page: 1 }, "", "/one");
        mockHistory.pushState({ page: 2 }, "", "/two");
        listen(mockNavigation, "navigate", (ev) =>
            steps.push(`navigate:${ev.navigationType}`),
        );
        listen(window, "popstate", (ev) => steps.push(`popstate:${ev.state.page}`));

        mockHistory.back();

        expect(steps).toEqual(["navigate:traverse", "popstate:1"]);
        expect(mockLocation.pathname).toBe("/one");
        expect(mockNavigation.canGoForward).toBe(true);
    });

    test("navigation: an intercepted navigate() commits its entry and runs the handler", async () => {
        const steps = [];
        listen(mockNavigation, "navigate", (ev) =>
            ev.intercept({ handler: () => steps.push(`handled:${ev.info}`) }),
        );
        const { finished } = mockNavigation.navigate("/target", {
            state: { s: 1 },
            info: "x",
        });
        await finished;

        expect(steps).toEqual(["handled:x"]);
        expect(mockLocation.pathname).toBe("/target");
        expect(mockNavigation.currentEntry.getState()).toEqual({ s: 1 });
    });

    test("navigation: traverseTo goes to the entry with that key, and an unknown key rejects", async () => {
        const start = mockNavigation.currentEntry.key;
        mockHistory.pushState(null, "", "/one");
        mockHistory.pushState(null, "", "/two");

        await mockNavigation.traverseTo(start).finished;
        expect(mockNavigation.currentEntry.key).toBe(start);

        await expect(mockNavigation.traverseTo("nope").finished).rejects.toThrow(
            /no entry/,
        );
    });

    test("navigation: a cancelled navigation leaves the location where it was", async () => {
        const href = mockLocation.href;
        listen(mockNavigation, "navigate", (ev) => ev.preventDefault());

        await expect(mockNavigation.navigate("/elsewhere").finished).rejects.toThrow(
            /cancelled/,
        );
        expect(mockLocation.href).toBe(href);
    });

    test("navigation: following a link is a user-initiated push, a modified click is not", async () => {
        const seen = [];
        listen(mockNavigation, "navigate", (ev) => {
            seen.push([ev.navigationType, ev.userInitiated, ev.downloadRequest]);
            ev.preventDefault();
        });
        const link = document.createElement("a");
        link.href = "/followed";
        const download = document.createElement("a");
        download.href = "/file.pdf";
        download.download = "file.pdf";
        document.body.append(link, download);
        after(() => {
            link.remove();
            download.remove();
        });

        link.dispatchEvent(
            new MouseEvent("click", { bubbles: true, cancelable: true }),
        );
        link.dispatchEvent(
            new MouseEvent("click", { bubbles: true, cancelable: true, ctrlKey: true }),
        );
        download.dispatchEvent(
            new MouseEvent("click", { bubbles: true, cancelable: true }),
        );

        expect(seen).toEqual([
            ["push", true, null],
            ["push", true, "file.pdf"],
        ]);
    });

    test("mock responses: error handling after reading body", async () => {
        mockFetch(() => "some text");

        const response = await fetch("/text");
        const responseClone = response.clone();
        const result = await response.text();

        expect(result).toBe("some text");

        await expect(response.arrayBuffer()).rejects.toThrow(TypeError);
        await expect(response.blob()).rejects.toThrow(TypeError);
        await expect(response.bytes()).rejects.toThrow(TypeError);
        await expect(response.formData()).rejects.toThrow(TypeError);
        await expect(response.json()).rejects.toThrow(TypeError);
        await expect(response.text()).rejects.toThrow(TypeError);

        const cloneResult = await responseClone.text();

        expect(cloneResult).toBe(result);

        await expect(responseClone.text()).rejects.toThrow(TypeError);
    });
});
