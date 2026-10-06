import {
    displayValues,
    savedValue,
    savedValues,
} from "@geoengine/geoengine/record_values";
import { describe, expect, test } from "@odoo/hoot";

describe("savedValues", () => {
    test("reads _values from a Record, ignoring unsaved changes", () => {
        const record = { _values: { name: "saved" }, data: { name: "edited" } };
        expect(savedValues(record).name).toBe("saved");
    });

    test("falls back to data when a Record exposes only that", () => {
        expect(savedValues({ data: { name: "only-data" } }).name).toBe("only-data");
    });

    test("treats a plain ORM dict as its own values", () => {
        expect(savedValues({ id: 7, name: "dict" }).name).toBe("dict");
    });

    test("never returns null for an absent datum", () => {
        expect(savedValues(undefined)).toEqual({});
        expect(savedValues(null)).toEqual({});
    });
});

describe("displayValues", () => {
    test("prefers data, so unsaved edits are what the popup shows", () => {
        const record = { _values: { name: "saved" }, data: { name: "edited" } };
        expect(displayValues(record).name).toBe("edited");
    });

    test("falls back to _values when there are no changes to overlay", () => {
        expect(displayValues({ _values: { name: "saved" } }).name).toBe("saved");
    });
});

describe("savedValue", () => {
    test("reads one field across all three shapes", () => {
        expect(savedValue({ _values: { qty: 1 } }, "qty")).toBe(1);
        expect(savedValue({ data: { qty: 2 } }, "qty")).toBe(2);
        expect(savedValue({ qty: 3 }, "qty")).toBe(3);
    });

    test("is undefined for a field nothing carries", () => {
        expect(savedValue({ _values: {} }, "missing")).toBe(undefined);
    });

    test("keeps a zero, which the classifier counts", () => {
        expect(savedValue({ _values: { grade: 0 } }, "grade")).toBe(0);
    });
});
