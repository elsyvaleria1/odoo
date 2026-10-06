import { describe, expect, test } from "@odoo/hoot";
import { click, waitFor } from "@odoo/hoot-dom";
import { expectRowsCoverHeaderGrid } from "@web/../tests/views/list/list_grid_test_helpers";
import {
    defineModels,
    fields,
    models,
    mountView,
    serverState,
} from "@web/../tests/web_test_helpers";
import { defineWebsiteSlidesModels } from "@website_slides/../tests/website_slides_test_helpers";

class Partner extends models.Model {
    lines = fields.One2many({ relation: "lines_sections" });

    _records = [{ id: 1, lines: [1, 2] }];
}

class LinesSections extends models.Model {
    _name = "lines_sections";
    display_name = fields.Char();
    name = fields.Char({ string: "Name" });
    is_category = fields.Boolean();
    int = fields.Integer({ string: "Integer" });
    sequence = fields.Integer();
    is_published = fields.Boolean();

    _records = [
        {
            id: 1,
            is_category: true,
            display_name: "firstSectionName",
            name: "firstSectionTitle",
            int: 4,
        },
        {
            id: 2,
            is_category: false,
            display_name: "recordName",
            name: "recordTitle",
            int: 5,
        },
    ];

    _views = {
        form: `
            <form>
                <field name="display_name"/>
            </form>
        `,
    };
}

defineWebsiteSlidesModels();
defineModels([LinesSections, Partner]);

test("basic rendering", async () => {
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `
            <form>
                <field name="lines" widget="slide_category_one2many">
                    <list>
                        <field name="is_category" column_invisible="1"/>
                        <field name="name"/>
                        <field name="display_name"/>
                        <field name="int"/>
                    </list>
                </field>
            </form>`,
    });
    expect(".o_field_x2many .o_list_renderer table.o_section_list_view").toHaveCount(1);
    expect(".o_data_row").toHaveCount(2);
    expect(".o_data_row:eq(0)").toHaveClass("o_is_section fw-bold");
    expect(".o_data_row:eq(0)").toHaveText("firstSectionTitle");
    expect(".o_data_row:eq(1)").toHaveText("recordTitle recordName 5");
    expect(".o_data_row:eq(0) td[name=name]:nth-child(1)").toHaveAttribute(
        "colspan",
        "3",
    );
    expect(".o_data_row:eq(1) td[name=name]:nth-child(1)").not.toHaveAttribute(
        "colspan",
    );
});

test("click on section behaves as usual in readonly mode", async () => {
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `
            <form>
                <field name="lines" widget="slide_category_one2many">
                    <list>
                        <field name="is_category" column_invisible="1"/>
                        <field name="name"/>
                        <field name="int"/>
                    </list>
                </field>
            </form>`,
        readonly: true,
    });
    await click(".o_data_cell:nth-child(1)");
    await waitFor(".modal .o_form_view");
    expect(".modal .o_form_view").toHaveCount(1);
    expect(".o_selected_row").toHaveCount(0);
});

test("click on section edit the section in place", async () => {
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `
            <form>
                <field name="lines" widget="slide_category_one2many">
                    <list>
                        <field name="is_category" column_invisible="1"/>
                        <field name="name"/>
                        <field name="int"/>
                    </list>
                </field>
            </form>`,
    });
    await click(".o_data_cell:nth-child(1)");
    await waitFor(".o_is_section.o_selected_row");
    expect(".o_is_section.o_selected_row").toHaveCount(1);
    expect(".modal .o_form_view").toHaveCount(0);
});

test("click on real line opens a dialog", async () => {
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `
            <form>
                <field name="lines" widget="slide_category_one2many">
                    <list>
                        <field name="is_category" column_invisible="1"/>
                        <field name="name"/>
                        <field name="int"/>
                    </list>
                </field>
            </form>`,
    });
    await click(".o_data_row:nth-child(2) .o_data_cell:nth-child(1)");
    await waitFor(".modal .o_form_view");
    expect(".modal .o_form_view").toHaveCount(1);
});

test.tags("desktop");
test("can create section inline", async () => {
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `
            <form>
                <field name="lines" widget="slide_category_one2many">
                    <list>
                        <field name="is_category" column_invisible="1"/>
                        <field name="name"/>
                        <field name="int"/>
                        <control>
                            <create string="add line"/>
                            <create string="add section" context="{'default_is_category': true}"/>
                        </control>
                    </list>
                </field>
            </form>`,
    });
    expect(".o_selected_row.o_is_section").toHaveCount(0);

    await click(".o_field_x2many_list_row_add a:nth-child(2)");
    await waitFor(".o_selected_row.o_is_section");
    expect(".o_selected_row.o_is_section").toHaveCount(1);
    expect(".modal .o_form_view").toHaveCount(0);
});

test("creates real record in form dialog", async () => {
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `
            <form>
                <field name="lines" widget="slide_category_one2many">
                    <list>
                        <field name="is_category" column_invisible="1"/>
                        <field name="name"/>
                        <field name="int"/>
                        <control>
                            <create string="add line"/>
                            <create string="add section" context="{'default_is_category': true}"/>
                        </control>
                    </list>
                </field>
            </form>`,
    });

    await click(".o_field_x2many_list_row_add a:nth-child(1)");
    await waitFor(".modal .o_form_view");
    expect(".o_selected_row").toHaveCount(0);
    expect(".modal .o_form_view").toHaveCount(1);
});

describe("category rows cover the header grid", () => {
    const SHIPPED_COLUMNS = `
        <field name="sequence" widget="handle"/>
        <field name="name"/>
        <field name="int"/>
        <field name="is_published" optional="hide"/>
        <field name="is_category" column_invisible="1"/>
    `;
    const configs = {
        "as the course form declares it": {
            list: '<list editable="bottom">',
            columns: SHIPPED_COLUMNS,
        },
        "readonly field": {
            list: '<list editable="bottom">',
            columns: SHIPPED_COLUMNS,
            fieldAttrs: 'readonly="1"',
        },
        "delete refused": {
            list: '<list editable="bottom" delete="0">',
            columns: SHIPPED_COLUMNS,
        },
        "not editable": { list: "<list>", columns: SHIPPED_COLUMNS },
        "optional column shown": {
            list: '<list editable="bottom">',
            columns: SHIPPED_COLUMNS.replace('optional="hide"', 'optional="show"'),
        },
        "handle placed after the title": {
            list: '<list editable="bottom">',
            columns: `
                <field name="name"/>
                <field name="sequence" widget="handle"/>
                <field name="int"/>
                <field name="is_category" column_invisible="1"/>
            `,
        },
        "a column before the title and the handle last": {
            list: '<list editable="bottom">',
            columns: `
                <field name="int"/>
                <field name="name"/>
                <field name="is_published"/>
                <field name="sequence" widget="handle"/>
                <field name="is_category" column_invisible="1"/>
            `,
        },
        "debug, delete refused, no optional column": {
            list: '<list editable="bottom" delete="0">',
            columns: `
                <field name="sequence" widget="handle"/>
                <field name="name"/>
                <field name="int"/>
                <field name="is_category" column_invisible="1"/>
            `,
            debug: true,
        },
    };
    for (const [label, { list, columns, fieldAttrs = "", debug }] of Object.entries(
        configs,
    )) {
        test(label, async () => {
            if (debug) {
                serverState.debug = "1";
            }
            await mountView({
                type: "form",
                resModel: "partner",
                resId: 1,
                arch: `
                    <form>
                        <field name="lines" widget="slide_category_one2many" ${fieldAttrs}>
                            ${list}${columns}</list>
                        </field>
                    </form>
                `,
            });
            expectRowsCoverHeaderGrid();
        });
    }
});
