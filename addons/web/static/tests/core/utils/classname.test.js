// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { mergeClasses } from "@web/core/utils/dom/classname";

describe.current.tags("headless");

describe("mergeClasses", () => {
    test("merges string classes into object", () => {
        const result = mergeClasses("foo bar");
        expect(result).toEqual({ foo: true, bar: true });
    });

    test("merges object classes", () => {
        const result = mergeClasses({ a: true, b: false });
        expect(result).toEqual({ a: true, b: false });
    });

    test("later definitions override earlier ones", () => {
        const result = mergeClasses({ active: true }, { active: false });
        expect(result).toEqual({ active: false });
    });

    test("merges multiple mixed sources", () => {
        const result = mergeClasses("base", { conditional: true }, "extra");
        expect(result).toEqual({ base: true, conditional: true, extra: true });
    });

    test("handles undefined in list", () => {
        const result = mergeClasses(undefined, "valid", undefined);
        expect(result).toEqual({ valid: true });
    });

    test("empty string produces empty object", () => {
        const result = mergeClasses("");
        expect(result).toEqual({});
    });
});
