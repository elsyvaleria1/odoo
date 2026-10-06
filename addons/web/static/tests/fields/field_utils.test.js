// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import {
    extractAutosave,
    extractImageDimensions,
    extractNumericOptions,
    isFalseEmpty,
    parseDimensionAttr,
} from "@web/fields/field_utils";

describe.current.tags("headless");

describe("extractAutosave", () => {
    test("defaults to true, and only an explicit option turns it off", () => {
        expect(extractAutosave({})).toBe(true);
        expect(extractAutosave({ autosave: true })).toBe(true);
        expect(extractAutosave({ autosave: "1" })).toBe(true);
        expect(extractAutosave({ autosave: false })).toBe(false);
        expect(extractAutosave({ autosave: "0" })).toBe(false);
    });

    test("presence is what matters, not truthiness", () => {
        expect(extractAutosave({ autosave: undefined })).toBe(false);
    });
});

describe("isFalseEmpty", () => {
    test("only literal false counts as empty", () => {
        const record = (/** @type {any} */ value) => ({ data: { f: value } });
        expect(isFalseEmpty(/** @type {any} */ (record(false)), "f")).toBe(true);
        expect(isFalseEmpty(/** @type {any} */ (record(0)), "f")).toBe(false);
        expect(isFalseEmpty(/** @type {any} */ (record("")), "f")).toBe(false);
        expect(isFalseEmpty(/** @type {any} */ (record(null)), "f")).toBe(false);
        expect(isFalseEmpty(/** @type {any} */ (record(undefined)), "f")).toBe(false);
    });
});

describe("parseDimensionAttr", () => {
    test("returns a number, or undefined for anything unusable", () => {
        expect(parseDimensionAttr("90")).toBe(90);
        expect(parseDimensionAttr(90)).toBe(90);
        expect(parseDimensionAttr("90px")).toBe(90);
        expect(parseDimensionAttr("")).toBe(undefined);
        expect(parseDimensionAttr(null)).toBe(undefined);
        expect(parseDimensionAttr(undefined)).toBe(undefined);
        expect(parseDimensionAttr("auto")).toBe(undefined);
    });

    test("a relative unit is not read as pixels", () => {
        expect(parseDimensionAttr("10%")).toBe(undefined);
        expect(parseDimensionAttr("100%")).toBe(undefined);
        expect(parseDimensionAttr("2em")).toBe(undefined);
        expect(parseDimensionAttr("1.5rem")).toBe(undefined);
        expect(parseDimensionAttr("90abc")).toBe(undefined);
        expect(parseDimensionAttr("-5")).toBe(undefined);
    });

    test("bare numbers and px, with decimals and spacing, are pixels", () => {
        expect(parseDimensionAttr(" 90 ")).toBe(90);
        expect(parseDimensionAttr("90PX")).toBe(90);
        expect(parseDimensionAttr("12.5px")).toBe(12.5);
        expect(parseDimensionAttr("0")).toBe(0);
        expect(parseDimensionAttr(12.5)).toBe(12.5);
        expect(parseDimensionAttr(Number.NaN)).toBe(undefined);
    });

    test("undefined and not NaN, because the caller spreads the result", () => {
        expect(Number.isNaN(parseDimensionAttr("auto"))).toBe(false);
    });
});

describe("extractNumericOptions", () => {
    test("the defaults every numeric widget inherits", () => {
        expect(extractNumericOptions({ options: {} })).toEqual({
            formatNumber: true,
            humanReadable: false,
            inputType: undefined,
            step: undefined,
            decimals: 0,
        });
    });

    test("enable_formatting is three-state, unlike the rest", () => {
        expect(extractNumericOptions({ options: {} }).formatNumber).toBe(true);
        expect(
            extractNumericOptions({ options: { enable_formatting: false } })
                .formatNumber,
        ).toBe(false);
        expect(
            extractNumericOptions({ options: { enable_formatting: 0 } }).formatNumber,
        ).toBe(false);
        expect(
            extractNumericOptions({ options: { enable_formatting: true } })
                .formatNumber,
        ).toBe(true);
    });

    test("passes the input pass-throughs straight down", () => {
        expect(
            extractNumericOptions({
                options: {
                    human_readable: "1",
                    type: "number",
                    step: 5,
                    decimals: 2,
                },
            }),
        ).toEqual({
            formatNumber: true,
            humanReadable: true,
            inputType: "number",
            step: 5,
            decimals: 2,
        });
    });
});

describe("extractImageDimensions", () => {
    test("the size option wins as a pair; a zero or empty entry means unset", () => {
        const attrs = { width: "50", height: "60" };
        expect(extractImageDimensions({ attrs, options: { size: [90, 90] } })).toEqual({
            width: 90,
            height: 90,
        });
        expect(extractImageDimensions({ attrs, options: { size: [0, 24] } })).toEqual({
            width: undefined,
            height: 24,
        });
        expect(extractImageDimensions({ attrs, options: { size: ["", 100] } })).toEqual(
            {
                width: undefined,
                height: 100,
            },
        );
    });

    test("a percentage attribute leaves the image unconstrained, not 10px wide", () => {
        expect(
            extractImageDimensions({
                attrs: { width: "10%", height: "40px" },
                options: {},
            }),
        ).toEqual({ width: undefined, height: 40 });
    });

    test("size entries given as strings are parsed like the attributes", () => {
        expect(
            extractImageDimensions({ attrs: {}, options: { size: ["90", "50%"] } }),
        ).toEqual({ width: 90, height: undefined });
    });

    test("without a size option the width/height attributes apply", () => {
        expect(
            extractImageDimensions({ attrs: { width: "30px" }, options: {} }),
        ).toEqual({ width: 30, height: undefined });
        expect(extractImageDimensions({ attrs: {}, options: {} })).toEqual({
            width: undefined,
            height: undefined,
        });
    });
});
