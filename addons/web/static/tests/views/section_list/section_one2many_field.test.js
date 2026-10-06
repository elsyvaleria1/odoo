import { describe, expect, test } from "@odoo/hoot";
import { expectRowsCoverHeaderGrid } from "@web/../tests/views/list/list_grid_test_helpers";
import {
    defineModels,
    fields,
    models,
    mountView,
    serverState,
} from "@web/../tests/web_test_helpers";

class Partner extends models.Model {
    lines = fields.One2many({ relation: "lines_sections" });
    _records = [
        {
            id: 1,
            lines: [1, 2],
        },
    ];
}

class LinesSections extends models.Model {
    _name = "lines_sections";

    display_type = fields.Char();
    display_name = fields.Char();
    int = fields.Integer();
    sequence = fields.Integer();

    _records = [
        {
            id: 1,
            display_type: "line_section",
            display_name: "firstSectionTitle",
            int: 4,
        },
        {
            id: 2,
            display_type: false,
            display_name: "recordTitle",
            int: 5,
        },
    ];
}

defineModels([Partner, LinesSections]);

const ARCH = `
    <form>
        <field name="lines" widget="section_one2many">
            <list>
                <field name="display_type" column_invisible="1" />
                <field name="display_name" />
                <field name="int" />
            </list>
        </field>
    </form>
`;

test("basic rendering", async () => {
    await mountView({ type: "form", resModel: "partner", resId: 1, arch: ARCH });
    expect(".o_field_x2many .o_list_renderer table.o_section_list_view").toHaveCount(1);
    expect(".o_data_row").toHaveCount(2);
    expect(".o_data_row:first").toHaveClass("o_is_line_section fw-bold");
    expect(".o_data_row:eq(1)").not.toHaveClass("o_is_line_section fw-bold");
    expect(".o_data_row:first").toHaveText("firstSectionTitle");
    expect(".o_data_row:eq(1)").toHaveText("recordTitle 5");
    expect(".o_data_row:first td[name=display_name]").toHaveAttribute("colspan", "2");
    expect(".o_data_row:eq(1) td[name=display_name]").not.toHaveAttribute("colspan");
    expect(".o_list_record_remove button[name=delete]").toHaveCount(1);
    expect(".o_is_line_section .o_list_record_remove button").toHaveCount(0);
});

test("section row shows its label rather than an empty band", async () => {
    await mountView({ type: "form", resModel: "partner", resId: 1, arch: ARCH });
    expect(".o_data_row:first").toHaveText("firstSectionTitle");
    expect(".o_data_row:first").not.toHaveText("");
});

test("a readonly section row spans the optional-columns cell the header has", async () => {
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `
            <form>
                <field name="lines" widget="section_one2many" readonly="1">
                    <list>
                        <field name="display_type" column_invisible="1" />
                        <field name="display_name" />
                        <field name="int" optional="show" />
                    </list>
                </field>
            </form>
        `,
    });
    const headerCells = document.querySelectorAll(".o_list_table thead tr th").length;
    const sectionSpan = [...document.querySelectorAll(".o_is_line_section td")].reduce(
        (total, td) => total + Number(td.getAttribute("colspan") || 1),
        0,
    );
    expect(".o_list_record_remove").toHaveCount(0);
    expect(sectionSpan).toBe(headerCells);
});

describe("section rows cover the header grid", () => {
    const configs = {
        "as the widget is declared": { columns: "" },
        "handle first": {
            columns: `<field name="sequence" widget="handle"/>`,
            before: true,
        },
        "handle placed after the title": {
            columns: `<field name="sequence" widget="handle"/>`,
            afterTitle: true,
        },
        "editable, delete refused": {
            columns: `<field name="sequence" widget="handle"/>`,
            listAttrs: 'editable="bottom" delete="0"',
        },
        "readonly field with an optional column": {
            columns: `<field name="sequence" optional="show"/>`,
            fieldAttrs: 'readonly="1"',
        },
        "debug, delete refused": {
            columns: `<field name="sequence" widget="handle"/>`,
            listAttrs: 'delete="0"',
            debug: true,
        },
    };
    for (const [label, config] of Object.entries(configs)) {
        test(label, async () => {
            if (config.debug) {
                serverState.debug = "1";
            }
            const extra = config.columns;
            await mountView({
                type: "form",
                resModel: "partner",
                resId: 1,
                arch: `
                    <form>
                        <field name="lines" widget="section_one2many" ${config.fieldAttrs ?? ""}>
                            <list ${config.listAttrs ?? ""}>
                                ${config.before ? extra : ""}
                                <field name="display_type" column_invisible="1" />
                                <field name="display_name" />
                                ${config.afterTitle ? extra : ""}
                                <field name="int" />
                                ${!config.before && !config.afterTitle ? extra : ""}
                            </list>
                        </field>
                    </form>
                `,
            });
            expectRowsCoverHeaderGrid();
        });
    }

    test("title column hidden by its optional toggle", async () => {
        await mountView({
            type: "form",
            resModel: "partner",
            resId: 1,
            arch: `
                <form>
                    <field name="lines" widget="section_one2many">
                        <list>
                            <field name="display_type" column_invisible="1" />
                            <field name="display_name" optional="hide" />
                            <field name="int" />
                        </list>
                    </field>
                </form>
            `,
        });
        expect(".o_list_table thead th[data-name=display_name]").toHaveCount(0);
        expect(".o_is_line_section td[name=display_name]").toHaveText(
            "firstSectionTitle",
        );
        expectRowsCoverHeaderGrid();
    });
});
