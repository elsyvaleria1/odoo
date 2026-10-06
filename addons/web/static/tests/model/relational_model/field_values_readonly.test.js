// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { fromUnityToServerValues } from "@web/model/relational_model/field_values";
import { computeChangeset } from "@web/model/relational_model/record_utils";

describe.current.tags("headless");

const FIELDS = {
    flag: { name: "flag", type: "boolean" },
    count: { name: "count", type: "integer" },
};

describe("fromUnityToServerValues readonly modifier", () => {
    test("a modifier evaluating to True strips the value", () => {
        const out = fromUnityToServerValues(
            { flag: true },
            FIELDS,
            { flag: { readonly: "True" } },
            { withReadonly: false, evalContext: {} },
        );
        expect(out).toEqual({});
    });

    test("a modifier evaluating to False keeps the value", () => {
        const out = fromUnityToServerValues(
            { flag: true },
            FIELDS,
            { flag: { readonly: "False" } },
            { withReadonly: false, evalContext: {} },
        );
        expect(out).toEqual({ flag: true });
    });

    test("a modifier evaluating to an empty list is Python-falsy (writable)", () => {
        const out = fromUnityToServerValues(
            { count: 5 },
            FIELDS,
            { count: { readonly: "ids" } },
            { withReadonly: false, evalContext: { ids: [] } },
        );
        expect(out).toEqual({ count: 5 });
    });

    test("a non-empty list modifier is Python-truthy (readonly), stripped", () => {
        const out = fromUnityToServerValues(
            { count: 5 },
            FIELDS,
            { count: { readonly: "ids" } },
            { withReadonly: false, evalContext: { ids: [1] } },
        );
        expect(out).toEqual({});
    });

    test("an unevaluable modifier stays writable (fail-open, unchanged)", () => {
        const out = fromUnityToServerValues(
            { count: 5 },
            FIELDS,
            { count: { readonly: "missing_var == 1" } },
            { withReadonly: false, evalContext: {} },
        );
        expect(out).toEqual({ count: 5 });
    });

    test("withReadonly=true bypasses the readonly gate entirely", () => {
        const out = fromUnityToServerValues(
            { flag: true },
            FIELDS,
            { flag: { readonly: "True" } },
            { withReadonly: true, evalContext: {} },
        );
        expect(out).toEqual({ flag: true });
    });

    test("a modifier reads the record's eval context, parent included", () => {
        const evalContext = { state: "done", parent: { locked: true } };
        expect(
            fromUnityToServerValues(
                { count: 5 },
                FIELDS,
                { count: { readonly: "state != 'draft'" } },
                { withReadonly: false, evalContext },
            ),
        ).toEqual({});
        expect(
            fromUnityToServerValues(
                { flag: true },
                FIELDS,
                { flag: { readonly: "parent.locked" } },
                { withReadonly: false, evalContext },
            ),
        ).toEqual({});
        expect(
            fromUnityToServerValues(
                { flag: true },
                FIELDS,
                { flag: { readonly: "not parent.locked" } },
                { withReadonly: false, evalContext },
            ),
        ).toEqual({ flag: true });
    });
});

describe("fromUnityToServerValues withholds what computeChangeset withholds", () => {
    test("force_save keeps a view-readonly value", () => {
        const out = fromUnityToServerValues(
            { count: 5 },
            FIELDS,
            { count: { readonly: "True", forceSave: true } },
            { withReadonly: false, evalContext: {} },
        );
        expect(out).toEqual({ count: 5 });
    });

    test("a Python-readonly field the view makes writable is kept", () => {
        const out = fromUnityToServerValues(
            { count: 5 },
            { count: { name: "count", type: "integer", readonly: true } },
            { count: { readonly: "False" } },
            { withReadonly: false, evalContext: {} },
        );
        expect(out).toEqual({ count: 5 });
    });

    test("both serializers agree on every readonly / force_save combination", () => {
        const fields = { count: { name: "count", type: "integer", readonly: true } };
        for (const readonly of ["True", "False", "state == 'done'"]) {
            for (const forceSave of [false, true]) {
                const activeFields = { count: { readonly, forceSave } };
                const evalContext = { state: "done" };
                const deferred = fromUnityToServerValues(
                    { count: 5 },
                    fields,
                    activeFields,
                    {
                        withReadonly: false,
                        evalContext,
                    },
                );
                const loaded = computeChangeset({
                    changes: { count: 5 },
                    values: {},
                    isNew: false,
                    fields,
                    activeFields,
                    evalContext,
                    getCommands: () => [],
                });
                expect(deferred).toEqual(loaded, {
                    message: `readonly=${readonly} forceSave=${forceSave}`,
                });
            }
        }
    });
});
