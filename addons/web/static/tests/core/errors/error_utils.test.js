// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import {
    fullAnnotatedTraceback,
    fullTraceback,
    getErrorTechnicalName,
} from "@web/core/errors/error_utils";

describe.current.tags("headless");

/**
 * @param {string} message
 * @param {unknown} [cause]
 */
function makeError(message, cause) {
    const error = new Error(message, cause !== undefined ? { cause } : undefined);
    error.stack = `Error: ${message}\n    at doThing (some_module.js:12:34)`;
    return error;
}

describe("fullTraceback", () => {
    test("walks the cause chain", () => {
        const root = makeError("root");
        const middle = makeError("middle", root);
        const top = makeError("top", middle);
        const traceback = fullTraceback(top);
        expect(traceback).toInclude("top");
        expect(traceback).toInclude("Caused by:");
        expect(traceback).toInclude("middle");
        expect(traceback).toInclude("root");
    });

    test("a non-Error cause is stringified rather than formatted", () => {
        expect(fullTraceback(makeError("top", "just a string"))).toInclude(
            "Caused by: just a string",
        );
    });

    test("a cyclic cause chain terminates", () => {
        const a = makeError("a");
        const b = makeError("b", a);
        /** @type {any} */ (a).cause = b;
        const traceback = fullTraceback(a);
        expect(traceback).toInclude("a");
        expect(traceback).toInclude("b");
        expect(traceback.match(/Caused by:/g)?.length).toBe(1);
    });
});

describe("fullAnnotatedTraceback", () => {
    test("returns the annotated traceback and caches it on the error", async () => {
        const error = makeError("plain");
        const traceback = await fullAnnotatedTraceback(error);
        expect(typeof traceback).toBe("string");
        expect(traceback).toInclude("plain");
        expect(/** @type {any} */ (error).annotatedTraceback).toBe(traceback);
    });

    test("resolves the cached traceback on a second call instead of annotating again", async () => {
        const error = makeError("second pass");
        const first = await fullAnnotatedTraceback(error);
        error.stack = "Error: changed\n    at elsewhere (other.js:1:1)";

        await expect(fullAnnotatedTraceback(error)).resolves.toBe(first);
    });
});

describe("getErrorTechnicalName", () => {
    test("prefers an explicit name over the constructor name", () => {
        class MyError extends Error {}
        expect(getErrorTechnicalName(new MyError("x"))).toBe("MyError");
        const named = new Error("x");
        named.name = "SomethingElse";
        expect(getErrorTechnicalName(named)).toBe("SomethingElse");
        expect(getErrorTechnicalName(new Error("x"))).toBe("Error");
    });
});
