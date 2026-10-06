// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { Operation } from "@web/core/utils/operation";

describe.current.tags("headless");

describe("Operation.compute", () => {
    test("adds operand to value", () => {
        expect(new Operation("+", 10).compute(5)).toBe(15);
        expect(new Operation("+", -3).compute(7)).toBe(4);
    });

    test("subtracts operand from value", () => {
        expect(new Operation("-", 3).compute(10)).toBe(7);
        expect(new Operation("-", 10).compute(3)).toBe(-7);
    });

    test("multiplies value by operand", () => {
        expect(new Operation("*", 4).compute(3)).toBe(12);
        expect(new Operation("*", 0).compute(100)).toBe(0);
    });

    test("divides value by operand", () => {
        expect(new Operation("/", 2).compute(10)).toBe(5);
        expect(new Operation("/", 4).compute(1)).toBe(0.25);
    });

    test("throws on unknown operator", () => {
        const unknownOperator = /** @type {any} */ ("%");
        expect(() => new Operation(unknownOperator, 3).compute(10)).toThrow(Error);
    });

    test("an integer operation truncates toward zero, like the integer column", () => {
        expect(new Operation("/", 3, { integer: true }).compute(10)).toBe(3);
        expect(new Operation("/", 2, { integer: true }).compute(-7)).toBe(-3);
        expect(new Operation("*", 2, { integer: true }).compute(5)).toBe(10);
        expect(new Operation("/", 3).compute(10)).toBeCloseTo(3.333, { margin: 0.001 });
    });

    test("handles negative values correctly", () => {
        expect(new Operation("+", 5).compute(-10)).toBe(-5);
        expect(new Operation("*", -1).compute(7)).toBe(-7);
    });
});
