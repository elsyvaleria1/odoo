// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { Domain } from "@web/core/domain";
import { condition } from "@web/core/tree/condition_tree";
import { constructDomainFromTree } from "@web/core/tree/construct_domain_from_tree";
import { expressionFromTree } from "@web/core/tree/expression_from_tree";
import { treeFromExpression } from "@web/core/tree/tree_from_expression";
import {
    eliminateVirtualOperators,
    introduceVirtualOperators,
} from "@web/core/tree/virtual_operators";

describe.current.tags("headless");

/**
 * @param {any} path
 * @param {string} operator
 * @param {any} value
 */
function eliminate(path, operator, value) {
    return constructDomainFromTree(
        eliminateVirtualOperators(condition(path, operator, value)),
    );
}

describe("eliminating a virtual operator keeps the path", () => {
    test("a plain path stays put", () => {
        expect(eliminate("amount", "between", [1, 5])).toBe(
            `["&", ("amount", ">=", 1), ("amount", "<=", 5)]`,
        );
    });

    test("a dotted path is split into an `any` subdomain", () => {
        expect(eliminate("line_ids.amount", "between", [1, 5])).toBe(
            `[("line_ids", "any", ["&", ("amount", ">=", 1), ("amount", "<=", 5)])]`,
        );
    });

    test("a non-string path survives", () => {
        expect(eliminate(1, "between", [1, 5])).toBe(
            `["&", (1, ">=", 1), (1, "<=", 5)]`,
        );
        expect(
            eliminate(1, "in range", [
                "date",
                "custom range",
                "2020-01-01",
                "2020-02-01",
            ]),
        ).toBe(`["&", (1, ">=", "2020-01-01"), (1, "<=", "2020-02-01")]`);
    });
});

describe("Domain.contains covers every operator the server defines", () => {
    test("the internal `any!` spellings are handled like `any`", () => {
        expect(new Domain([["id", "any!", [1]]]).contains({ id: 1 })).toBe(true);
        expect(new Domain([["id", "not any!", [1]]]).contains({ id: 1 })).toBe(false);
        expect(new Domain([["id", "any", [1]]]).contains({ id: 1 })).toBe(true);
        expect(new Domain([["id", "not any", [1]]]).contains({ id: 1 })).toBe(false);
    });

    test("an operator the server does not define is still refused", () => {
        expect(() => new Domain([["id", "wat", 1]]).contains({ id: 1 })).toThrow(
            /could not match domain/,
        );
    });
});

describe("Domain singletons are immutable", () => {
    test("TRUE and FALSE cannot be edited out from under their readers", () => {
        expect(Object.isFrozen(Domain.TRUE)).toBe(true);
        expect(Object.isFrozen(Domain.TRUE.ast.value)).toBe(true);
        expect(() => Domain.TRUE.ast.value.push(/** @type {any} */ ({}))).toThrow();
        expect(Domain.TRUE.toString()).toBe(`[(1, "=", 1)]`);
        expect(Domain.FALSE.toString()).toBe(`[(0, "=", 1)]`);
    });
});

describe("starts with", () => {
    const options = { getFieldDef: () => ({ type: "char" }) };

    test("escapes the LIKE wildcards of the prefix it writes", () => {
        expect(
            eliminateVirtualOperators(condition("name", "starts with", "5%_a\\")),
        ).toEqual(condition("name", "=ilike", "5\\%\\_a\\\\%"));
    });

    test("reads back only a pattern that is a plain prefix, unescaped", () => {
        const read = (/** @type {string} */ pattern) =>
            introduceVirtualOperators(condition("name", "=ilike", pattern), options);
        expect(read("5\\%\\_a\\\\%")).toEqual(
            condition("name", "starts with", "5%_a\\"),
        );
        expect(read("abc%")).toEqual(condition("name", "starts with", "abc"));
        expect(read("%foo%")).toEqual(condition("name", "=ilike", "%foo%"));
        expect(read("f_o%")).toEqual(condition("name", "=ilike", "f_o%"));
        expect(read("foo\\%")).toEqual(condition("name", "=ilike", "foo\\%"));
    });
});

describe("expressions never carry smart dates", () => {
    const options = {
        getFieldDef: (/** @type {any} */ name) =>
            name === "date_1" ? { type: "date" } : null,
    };
    const lastWeek = condition("date_1", "in range", [
        "date",
        "last 7 days",
        false,
        false,
    ]);

    test("an in-range condition is written as Python date arithmetic", () => {
        const written = expressionFromTree(lastWeek, options);
        expect(written).not.toInclude("today -7d");
        expect(written).toInclude("context_today()");
    });

    test("the written expression reads back as the same range", () => {
        expect(
            treeFromExpression(expressionFromTree(lastWeek, options), options),
        ).toEqual(lastWeek);
    });
});
