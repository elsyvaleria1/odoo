// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import {
    defineModels,
    fields,
    models,
    mountView,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import {
    Field,
    fieldLabelFeedback,
    fieldVisualFeedback,
    getFieldFromRegistry,
    getPropertyFieldInfo,
    resetWidgetMissWarnings,
} from "@web/fields/field";
import { parseFieldNode } from "@web/views/field_arch";

class Partner extends models.Model {
    _name = "res.partner";
    name = fields.Char();
    _records = [{ id: 1, name: "a" }];
}
defineModels([Partner]);

test("duplicate field widgets preserve their own context objects across renders", async () => {
    const seen = [];
    const owners = [];
    patchWithCleanup(Field.prototype, {
        setup() {
            super.setup(...arguments);
            owners.push(this);
        },
    });
    class Probe extends Component {
        static props = null;
        static template = xml`<span t-out="this.props.record.data.name"/>`;
        props = useProps(this.constructor.props);
    }
    registry.category("fields").add("context_owner_probe", {
        component: Probe,
        supportedTypes: ["char"],
        extractProps(_fieldInfo, dynamicInfo) {
            seen.push(dynamicInfo.context);
            return {};
        },
    });
    await mountView({
        resModel: "res.partner",
        resId: 1,
        type: "form",
        arch: `<form><field name="name" widget="context_owner_probe" context="{'limit': 10, 'label': name}"/><field name="name" widget="context_owner_probe" context="{'limit': 20, 'label': name}"/></form>`,
    });
    expect(owners).toHaveLength(2);
    await Promise.all(owners.map((owner) => owner.__owl__.render(true)));
    await animationFrame();
    makeLogger("web.model.audit").logic(
        "rendered field context owners",
        JSON.stringify({ owners: owners.length, reads: seen.length, contexts: seen }),
    );
    for (const limit of [10, 20]) {
        const contexts = seen.filter((context) => context.limit === limit);
        expect(contexts.length).toBeGreaterThan(1);
        expect(contexts.every((context) => context === contexts[0])).toBe(true);
    }
    await owners[0].props.record.update({ name: "b" });
    await animationFrame();
    expect(owners).toHaveLength(2);
    expect(seen.slice(-2).map((context) => context.label)).toEqual(["b", "b"]);
    await Promise.all(owners.map((owner) => owner.__owl__.render(true)));
    await animationFrame();
    makeLogger("web.model.audit").logic(
        "reactive field contexts",
        JSON.stringify(seen),
    );
    for (const limit of [10, 20]) {
        const previous = seen.find(
            (context) => context.limit === limit && context.label === "a",
        );
        const changed = seen.filter(
            (context) => context.limit === limit && context.label === "b",
        );
        expect(changed.length).toBeGreaterThan(1);
        expect(changed[0]).not.toBe(previous);
        expect(changed.every((context) => context === changed[0])).toBe(true);
    }
});

/** @param {Partial<any>} [overrides] */
/**
 * @param {Record<string, any>} [overrides]
 * @returns {any}
 */
function fakeRecord(overrides = {}) {
    return {
        isNew: false,
        isInEdition: false,
        data: { f: "value" },
        evalContextWithVirtualIds: {},
        isFieldInvalid: () => false,
        ...overrides,
    };
}

describe("fieldLabelFeedback", () => {
    test("a label never evaluates the required expression", () => {
        const record = fakeRecord({
            evalContextWithVirtualIds: {
                get flag() {
                    throw new Error("required read");
                },
            },
        });
        const feedback = fieldLabelFeedback({}, record, "f", {
            readonly: "False",
            required: "flag",
        });
        expect(feedback).toEqual({ readonly: false, invalid: false, empty: false });
    });

    test("agrees with the full feedback on everything a label shows", () => {
        const record = fakeRecord({ data: { f: false }, isFieldInvalid: () => true });
        const fieldInfo = { readonly: "True", required: "True" };
        const { required, ...rest } = fieldVisualFeedback({}, record, "f", fieldInfo);
        expect(required).toBe(true);
        expect(fieldLabelFeedback({}, record, "f", fieldInfo)).toEqual(rest);
    });
});

describe("fieldVisualFeedback", () => {
    test("falls back to the record value when no isEmpty hook is declared", () => {
        expect(fieldVisualFeedback({}, fakeRecord(), "f", {}).empty).toBe(false);
        expect(
            fieldVisualFeedback({}, fakeRecord({ data: { f: false } }), "f", {}).empty,
        ).toBe(true);
    });

    test("a declared isEmpty hook wins over the record value", () => {
        const field = { isEmpty: () => true };
        expect(fieldVisualFeedback(field, fakeRecord(), "f", {}).empty).toBe(true);
    });

    test("a new record is never empty", () => {
        const record = fakeRecord({ isNew: true, data: { f: false } });
        expect(fieldVisualFeedback({}, record, "f", {}).empty).toBe(false);
    });

    test("an explicitly-undefined isEmpty falls back instead of throwing", () => {
        expect(
            fieldVisualFeedback({ isEmpty: undefined }, fakeRecord(), "f", {}).empty,
        ).toBe(false);
        expect(
            fieldVisualFeedback(
                { isEmpty: undefined },
                fakeRecord({ data: { f: false } }),
                "f",
                {},
            ).empty,
        ).toBe(true);
    });

    test("an explicitly-undefined isValid falls back to the record", () => {
        expect(
            fieldVisualFeedback({ isValid: undefined }, fakeRecord(), "f", {}).invalid,
        ).toBe(false);
    });

    test("the registry accepts an entry carrying isEmpty: undefined", () => {
        class Probe extends Component {
            static template = xml``;
            static props = null;
            props = useProps(this.constructor.props);
        }
        const reg = registry.category("fields");
        expect(() =>
            reg.add("test_field_undefined_hooks", {
                component: Probe,
                isEmpty: undefined,
                isValid: undefined,
            }),
        ).not.toThrow();
        expect(
            fieldVisualFeedback(
                reg.get("test_field_undefined_hooks"),
                fakeRecord(),
                "f",
                {},
            ).empty,
        ).toBe(false);
    });

    test("readonly and required come from their fieldInfo expressions", () => {
        const record = fakeRecord({ evalContextWithVirtualIds: { flag: true } });
        const on = fieldVisualFeedback({}, record, "f", {
            readonly: "flag",
            required: "True",
        });
        expect(on.readonly).toBe(true);
        expect(on.required).toBe(true);
        const off = fieldVisualFeedback({}, record, "f", {});
        expect(off.readonly).toBe(false);
        expect(off.required).toBe(false);
    });

    test("required is a snapshot taken with the rest, not read later", () => {
        const evalContextWithVirtualIds = { flag: true };
        const record = fakeRecord({ evalContextWithVirtualIds });
        const feedback = fieldVisualFeedback({}, record, "f", {
            readonly: "flag",
            required: "flag",
        });
        evalContextWithVirtualIds.flag = false;
        expect(feedback.readonly).toBe(true);
        expect(feedback.required).toBe(true);
        expect(typeof Object.getOwnPropertyDescriptor(feedback, "required")?.get).toBe(
            "undefined",
        );
    });
});

describe("getFieldFromRegistry", () => {
    test("resolves by widget, then by view prefix, then by bare type", () => {
        expect(getFieldFromRegistry("char", "char").component.name).toBe("CharField");
        expect(getFieldFromRegistry("char").component.name).toBe("CharField");
        expect(getFieldFromRegistry("text", "text", "list").component.name).toBe(
            "ListTextField",
        );
        expect(getFieldFromRegistry("text", "text").component.name).toBe("TextField");
    });

    test("an unknown widget falls back to the type's default component", () => {
        resetWidgetMissWarnings();
        expect(getFieldFromRegistry("char", "no_such_widget").component.name).toBe(
            "CharField",
        );
    });

    test("an unknown widget on an unknown type yields DefaultField", () => {
        resetWidgetMissWarnings();
        expect(
            getFieldFromRegistry("no_such_type", "no_such_widget").component.name,
        ).toBe("DefaultField");
    });
});

describe("getPropertyFieldInfo", () => {
    test("carries the viewType it is given", () => {
        expect(getPropertyFieldInfo({ name: "p", type: "char" }, "list").viewType).toBe(
            "list",
        );
        expect(
            getPropertyFieldInfo({ name: "p", type: "char" }, "kanban").viewType,
        ).toBe("kanban");
    });

    test("resolves the view-prefixed registry entry, not just the bare one", () => {
        const componentFor = (
            /** @type {any} */ propertyField,
            /** @type {any} */ viewType,
        ) => getPropertyFieldInfo(propertyField, viewType).field.component.name;

        expect(componentFor({ name: "p", type: "text" }, "list")).toBe("ListTextField");
        expect(componentFor({ name: "p", type: "text" }, "form")).toBe("TextField");

        expect(componentFor({ name: "p", type: "datetime" }, "list")).toBe(
            "ListDateTimeField",
        );
        expect(componentFor({ name: "p", type: "datetime" }, "form")).toBe(
            "DateTimeField",
        );

        expect(
            componentFor(
                { name: "p", type: "many2many", relation: "res.users" },
                "list",
            ),
        ).toBe("ListMany2ManyTagsAvatarField");
        expect(
            componentFor(
                { name: "p", type: "many2many", relation: "res.users" },
                "kanban",
            ),
        ).toBe("KanbanMany2ManyTagsAvatarField");

        expect(componentFor({ name: "p", type: "text" }, undefined)).toBe("TextField");
    });

    test("relational properties on res.users/res.partner get the avatar widgets", () => {
        expect(
            getPropertyFieldInfo({ name: "p", type: "many2one", relation: "res.users" })
                .widget,
        ).toBe("many2one_avatar");
        expect(
            getPropertyFieldInfo({
                name: "p",
                type: "many2many",
                relation: "res.partner",
            }).widget,
        ).toBe("many2many_tags_avatar");
        expect(
            getPropertyFieldInfo({ name: "p", type: "many2many", relation: "other" })
                .widget,
        ).toBe("many2many_tags");
    });

    test("agrees on shape with parseFieldNode, the other producer", () => {
        const node = new DOMParser().parseFromString(
            `<field name="name"/>`,
            "text/xml",
        ).documentElement;
        const arch = parseFieldNode(
            node,
            { "res.partner": { fields: { name: { type: "char", string: "N" } } } },
            "res.partner",
            "list",
            /** @type {any} */ (null),
        );
        const property = getPropertyFieldInfo(
            { name: "name", type: "char", string: "N" },
            "list",
        );
        const onlyArch = Object.keys(arch)
            .filter((k) => !(k in property))
            .sort();
        const onlyProperty = Object.keys(property)
            .filter((k) => !(k in arch) && k !== "relatedPropertyField")
            .sort();
        expect({ onlyArch, onlyProperty }).toEqual({ onlyArch: [], onlyProperty: [] });
    });
});
