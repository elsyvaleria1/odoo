// @ts-check

import { expect, test } from "@odoo/hoot";
import { assertType, t } from "@odoo/owl";
import { fieldProps } from "@web/fields/field";
import { standardFieldProps } from "@web/fields/standard_field_props";
import { STANDARD_PROPS, viewProps } from "@web/views/view";

test("every STANDARD_PROPS key carries a declared type in viewProps", () => {
    const undeclared = STANDARD_PROPS.filter((key) => !(key in viewProps));
    expect(undeclared).toEqual([], {
        message:
            `these props are consumed by View (so they are NOT forwarded to the ` +
            `controller) but have no declared type, so passing the wrong thing ` +
            `for one of them is silent: ${undeclared.join(", ")}`,
    });
});

test("viewProps stays open, so unknown props still reach the controller", () => {
    expect(() =>
        assertType(
            { resModel: "res.partner", type: "list", someAddonProp: 42 },
            t.object(viewProps),
        ),
    ).not.toThrow();
});

test("viewProps rejects a wrongly-typed known prop", () => {
    expect(() =>
        assertType({ resModel: "res.partner", type: "list" }, t.object(viewProps)),
    ).not.toThrow();
    expect(() =>
        assertType(
            { resModel: "res.partner", type: "list", domain: "[]" },
            t.object(viewProps),
        ),
    ).toThrow();
    expect(() =>
        assertType(
            { resModel: "res.partner", type: "list", loadIrFilters: "yes" },
            t.object(viewProps),
        ),
    ).toThrow();
    expect(() =>
        assertType(
            { resModel: "res.partner", type: "list", groupBy: [1, 2] },
            t.object(viewProps),
        ),
    ).toThrow();
});

test("resModel and type stay optional so setup() owns those two messages", () => {
    expect(() => assertType({}, t.object(viewProps))).not.toThrow();
});

test("fieldProps extends standardFieldProps and stays open", () => {
    for (const key of Object.keys(standardFieldProps)) {
        expect(key in fieldProps).toBe(true, {
            message: `Field must keep validating the standard field prop "${key}"`,
        });
    }
    expect(() =>
        assertType(
            { name: "foo", record: {}, someWidgetOption: true },
            t.object(fieldProps),
        ),
    ).not.toThrow();
});

test("fieldProps rejects a wrongly-typed prop Field itself reads", () => {
    expect(() =>
        assertType({ name: "foo", record: {} }, t.object(fieldProps)),
    ).not.toThrow();
    expect(() => assertType({ name: 42, record: {} }, t.object(fieldProps))).toThrow();
    expect(() =>
        assertType({ name: "foo", record: {}, readonly: "1" }, t.object(fieldProps)),
    ).toThrow();
    expect(() =>
        assertType(
            { name: "foo", record: {}, fieldInfo: "nope" },
            t.object(fieldProps),
        ),
    ).toThrow();
    expect(() => assertType({ name: "foo" }, t.object(fieldProps))).toThrow();
});
