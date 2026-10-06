// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { click, press, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import {
    defineModels,
    fields,
    models,
    mountView,
    webModels,
} from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";

describe.current.tags("desktop");

class Foo extends models.Model {
    foo = fields.Char();
    int_field = fields.Integer();
    bar = fields.Boolean();
    m2o = fields.Many2one({ relation: "bar" });

    _records = [
        { id: 1, foo: "yop", int_field: 10, bar: true, m2o: 1 },
        { id: 2, foo: "blip", int_field: 9, bar: true, m2o: 1 },
        { id: 3, foo: "gnap", int_field: 17, bar: false, m2o: 2 },
    ];
}

class Bar extends models.Model {
    name = fields.Char();

    _records = [
        { id: 1, name: "Value 1" },
        { id: 2, name: "Value 2" },
    ];
}

defineModels([...Object.values(webModels), Foo, Bar]);

class InertWidget extends Component {
    static template = xml`<span class="inert_widget">w</span>`;
    static props = null;
    props = useProps(this.constructor.props);
}
registry.category("view_widgets").add("inert_widget", { component: InertWidget });

class ButtonWidget extends Component {
    static template = xml`<button class="btn btn-link button_widget">go</button>`;
    static props = null;
    props = useProps(this.constructor.props);
}
registry.category("view_widgets").add("button_widget", { component: ButtonWidget });

function describeFocus() {
    const active = /** @type {HTMLElement} */ (document.activeElement);
    if (active.classList.contains("o_searchview_input")) {
        return "search";
    }
    const cell = /** @type {HTMLTableCellElement | null} */ (active.closest("td, th"));
    const row = cell?.parentElement;
    if (!cell || !row) {
        return active.tagName.toLowerCase();
    }
    let rowName;
    if (row.closest("thead")) {
        rowName = "head";
    } else if (row.closest("tfoot")) {
        rowName = "foot";
    } else if (row.classList.contains("o_group_header")) {
        rowName = `g${row.dataset.rowIndex}`;
    } else {
        rowName = `r${row.dataset.rowIndex}`;
    }
    let cellName;
    if (cell.classList.contains("o_list_record_selector")) {
        cellName = "sel";
    } else if (cell.getAttribute("name") || cell.dataset.name) {
        cellName = /** @type {string} */ (
            cell.getAttribute("name") || cell.dataset.name
        );
    } else if (cell.classList.contains("o_group_name")) {
        cellName = "name";
    } else {
        cellName = `#${[...row.children].indexOf(cell)}`;
    }
    return `${rowName}:${cellName}`;
}

/** @param {string[]} keys */
async function trace(keys) {
    const out = [];
    for (const key of keys) {
        await press(key);
        await animationFrame();
        out.push(`${key}>${describeFocus()}`);
    }
    return out;
}

test("ArrowLeft/Right skip a widget cell that holds nothing focusable", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list>
                <field name="foo"/>
                <widget name="inert_widget"/>
                <field name="int_field"/>
            </list>`,
    });
    expect(`.o_searchview_input`).toBeFocused();
    expect(
        await trace([
            "ArrowDown",
            "ArrowDown",
            "ArrowRight",
            "ArrowRight",
            "ArrowLeft",
        ]),
    ).toEqual([
        "ArrowDown>head:sel",
        "ArrowDown>r0:sel",
        "ArrowRight>r0:foo",
        "ArrowRight>r0:int_field",
        "ArrowLeft>r0:foo",
    ]);
});

test("ArrowLeft/Right skip consecutive unfocusable cells and stop at the edge", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list>
                <field name="foo"/>
                <widget name="inert_widget"/>
                <widget name="inert_widget"/>
                <field name="int_field"/>
                <widget name="inert_widget"/>
            </list>`,
    });
    expect(
        await trace([
            "ArrowDown",
            "ArrowDown",
            "ArrowRight",
            "ArrowRight",
            "ArrowRight",
            "ArrowLeft",
        ]),
    ).toEqual([
        "ArrowDown>head:sel",
        "ArrowDown>r0:sel",
        "ArrowRight>r0:foo",
        "ArrowRight>r0:int_field",
        "ArrowRight>r0:int_field",
        "ArrowLeft>r0:foo",
    ]);
});

test("ArrowLeft/Right cross an unfocusable header cell", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list>
                <field name="foo"/>
                <widget name="inert_widget"/>
                <field name="int_field"/>
            </list>`,
    });
    expect(await trace(["ArrowDown", "ArrowRight", "ArrowRight", "ArrowLeft"])).toEqual(
        [
            "ArrowDown>head:sel",
            "ArrowRight>head:foo",
            "ArrowRight>head:int_field",
            "ArrowLeft>head:foo",
        ],
    );
});

test("ArrowUp onto a header cell that cannot take focus lands on the nearest one", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list>
                <field name="foo"/>
                <button name="do_it" type="object" string="Do"/>
            </list>`,
    });
    expect(
        await trace([
            "ArrowDown",
            "ArrowDown",
            "ArrowRight",
            "ArrowRight",
            "ArrowDown",
        ]),
    ).toEqual([
        "ArrowDown>head:sel",
        "ArrowDown>r0:sel",
        "ArrowRight>r0:foo",
        "ArrowRight>r0:#2",
        "ArrowDown>r1:#2",
    ]);
    expect(await trace(["ArrowUp", "ArrowUp", "ArrowUp"])).toEqual([
        "ArrowUp>r0:#2",
        "ArrowUp>head:foo",
        "ArrowUp>search",
    ]);
});

test("the empty actions cell of a grouped list does not trap the arrow keys", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        groupBy: ["bar"],
        arch: `<list><field name="foo"/></list>`,
    });
    await press("ArrowDown");
    await press("ArrowDown");
    await press("ArrowRight");
    await animationFrame();
    expect(
        await trace([
            "ArrowDown",
            "ArrowRight",
            "ArrowRight",
            "ArrowLeft",
            "ArrowLeft",
        ]),
    ).toEqual([
        "ArrowDown>r1:sel",
        "ArrowRight>r1:foo",
        "ArrowRight>r1:#2",
        "ArrowLeft>r1:foo",
        "ArrowLeft>r1:sel",
    ]);
    expect(await trace(["ArrowRight", "ArrowRight", "ArrowDown", "ArrowUp"])).toEqual([
        "ArrowRight>r1:foo",
        "ArrowRight>r1:#2",
        "ArrowDown>g2:name",
        "ArrowUp>r1:#2",
    ]);
});

test("ArrowUp from the first group header reaches the header row, and only the header row leaves for the search", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        groupBy: ["bar"],
        arch: `
            <list>
                <field name="foo"/>
                <button name="do_it" type="object" string="Do"/>
            </list>`,
    });
    expect(
        await trace([
            "ArrowDown",
            "ArrowDown",
            "ArrowRight",
            "ArrowDown",
            "ArrowRight",
            "ArrowRight",
            "ArrowUp",
            "ArrowUp",
            "ArrowUp",
        ]),
    ).toEqual([
        "ArrowDown>head:sel",
        "ArrowDown>g0:name",
        "ArrowRight>g0:name",
        "ArrowDown>r1:sel",
        "ArrowRight>r1:foo",
        "ArrowRight>r1:#2",
        "ArrowUp>g0:name",
        "ArrowUp>head:foo",
        "ArrowUp>search",
    ]);
});

test("ArrowUp from the first group header lands on the remembered header cell", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        groupBy: ["bar"],
        arch: `<list><field name="foo"/></list>`,
    });
    expect(await trace(["ArrowDown", "ArrowDown", "ArrowUp", "ArrowUp"])).toEqual([
        "ArrowDown>head:sel",
        "ArrowDown>g0:name",
        "ArrowUp>head:sel",
        "ArrowUp>search",
    ]);
});

test("the footer's 'Add a group' button does not trap the arrow keys", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `<list default_group_by="m2o"><field name="foo"/></list>`,
    });
    expect(
        await trace([
            "ArrowDown",
            "ArrowDown",
            "ArrowDown",
            "ArrowDown",
            "ArrowRight",
            "ArrowUp",
            "ArrowDown",
            "ArrowDown",
        ]),
    ).toEqual([
        "ArrowDown>head:sel",
        "ArrowDown>g0:name",
        "ArrowDown>g1:name",
        "ArrowDown>foot:#0",
        "ArrowRight>foot:#0",
        "ArrowUp>g1:name",
        "ArrowDown>foot:#0",
        "ArrowDown>foot:#0",
    ]);
    expect(".o_list_footer .o_list_group_add").toBeFocused();
});

test("the footer's group input keeps the arrow keys while its caret can move", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `<list default_group_by="m2o"><field name="foo"/></list>`,
    });
    await click(".o_list_footer .o_list_group_add");
    await animationFrame();
    const input = /** @type {HTMLInputElement} */ (queryOne(".o_list_group_input"));
    expect(input).toBeFocused();
    input.value = "ab";
    input.setSelectionRange(1, 1);
    expect(await trace(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"])).toEqual([
        "ArrowUp>foot:#0",
        "ArrowDown>foot:#0",
        "ArrowLeft>foot:#0",
        "ArrowRight>foot:#0",
    ]);
    expect(input).toBeFocused();
    input.setSelectionRange(2, 2);
    expect(await trace(["ArrowDown", "ArrowRight"])).toEqual([
        "ArrowDown>foot:#0",
        "ArrowRight>foot:#0",
    ]);
    expect(input).toBeFocused();
    input.setSelectionRange(0, 0);
    expect(await trace(["ArrowLeft", "ArrowUp"])).toEqual([
        "ArrowLeft>foot:#0",
        "ArrowUp>g1:name",
    ]);
});

test("the optional-columns toggle is reached by the arrow keys from its row and column", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list>
                <field name="foo"/>
                <field name="int_field" optional="show"/>
            </list>`,
    });
    expect(
        await trace([
            "ArrowDown",
            "ArrowRight",
            "ArrowRight",
            "ArrowRight",
            "ArrowRight",
        ]),
    ).toEqual([
        "ArrowDown>head:sel",
        "ArrowRight>head:foo",
        "ArrowRight>head:int_field",
        "ArrowRight>head:#3",
        "ArrowRight>head:#3",
    ]);
    expect(".o_optional_columns_dropdown button").toBeFocused();
    expect(await trace(["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"])).toEqual([
        "ArrowDown>r0:#3",
        "ArrowUp>head:#3",
        "ArrowLeft>head:int_field",
        "ArrowRight>head:#3",
    ]);
    await press("Enter");
    await animationFrame();
    expect(".o_optional_columns_menu").toHaveCount(1);
});

test("arrow keys on the open optional-columns dropdown drive its menu, not the list", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list>
                <field name="foo"/>
                <field name="int_field" optional="show"/>
            </list>`,
    });
    await click(".o_optional_columns_dropdown button");
    await animationFrame();
    expect(".o_optional_columns_menu").toHaveCount(1);
    await press("ArrowDown");
    await animationFrame();
    expect(".o_optional_columns_menu").toHaveCount(1);
    expect(document.activeElement.closest(".o_list_table")).toBe(null);
});

test("a widget cell holding a control does not trap the arrow keys", async () => {
    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list>
                <field name="foo"/>
                <widget name="button_widget"/>
                <field name="int_field"/>
            </list>`,
    });
    expect(
        await trace([
            "ArrowDown",
            "ArrowDown",
            "ArrowRight",
            "ArrowRight",
            "ArrowRight",
            "ArrowLeft",
            "ArrowDown",
            "ArrowUp",
        ]),
    ).toEqual([
        "ArrowDown>head:sel",
        "ArrowDown>r0:sel",
        "ArrowRight>r0:foo",
        "ArrowRight>r0:#2",
        "ArrowRight>r0:int_field",
        "ArrowLeft>r0:#2",
        "ArrowDown>r1:#2",
        "ArrowUp>r0:#2",
    ]);
    await press("Enter");
    await animationFrame();
    expect(".o_list_view").toHaveCount(1);
});
