import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, queryAll, test } from "@odoo/hoot";
import { expectRowsCoverHeaderGrid } from "@web/../tests/views/list/list_grid_test_helpers";
import {
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    serverState,
} from "@web/../tests/web_test_helpers";

class ColumnsLine extends models.Model {
    _name = "columns_line";
    _records = [
        { id: 1, name: "A", display_type: "line_section", sequence: 1 },
        {
            id: 2,
            name: "A1",
            sequence: 2,
            price_subtotal: 10,
            tax_amount: 1,
            price_total: 11,
        },
        { id: 3, name: "Aa", display_type: "line_subsection", sequence: 3 },
        {
            id: 4,
            name: "Aa1",
            sequence: 4,
            price_subtotal: 5,
            tax_amount: 1,
            price_total: 6,
        },
        { id: 5, name: "a note", display_type: "line_note", sequence: 5 },
    ];

    name = fields.Char();
    display_type = fields.Selection({
        default: false,
        selection: [
            ["line_section", "Section"],
            ["line_subsection", "Subsection"],
            ["line_note", "Note"],
        ],
    });
    sequence = fields.Integer();
    product = fields.Char();
    price_subtotal = fields.Float();
    tax_amount = fields.Float();
    price_total = fields.Float();
    lead = fields.Integer();
    collapse_composition = fields.Boolean({ default: false });
    collapse_prices = fields.Boolean({ default: false });
}

class ColumnsInvoice extends models.Model {
    _name = "columns_invoice";
    _records = [{ id: 1, line_ids: [1, 2, 3, 4, 5] }];

    line_ids = fields.One2many({ relation: "columns_line" });
}

class ColumnsMergeLine extends models.Model {
    _name = "columns_merge_line";
    _records = [
        { id: 1, info: "Group", display_type: "line_section", sequence: 1 },
        {
            id: 2,
            info: "401000",
            display_type: "account",
            sequence: 2,
            is_selected: true,
        },
    ];

    is_selected = fields.Boolean();
    account = fields.Char();
    companies = fields.Char();
    info = fields.Char();
    sequence = fields.Integer();
    display_type = fields.Selection({
        selection: [
            ["line_section", "Section"],
            ["account", "Account"],
        ],
    });
}

class ColumnsMergeWizard extends models.Model {
    _name = "columns_merge_wizard";
    _records = [{ id: 1, wizard_line_ids: [1, 2] }];

    wizard_line_ids = fields.One2many({ relation: "columns_merge_line" });
}

defineModels([ColumnsLine, ColumnsInvoice, ColumnsMergeLine, ColumnsMergeWizard]);
defineMailModels();

onRpc("has_group", () => true);

function invoiceArch({ fieldAttrs = "", listAttrs = 'editable="bottom"', columns }) {
    return `
        <form>
            <field name="line_ids" widget="section_and_note_one2many"
                   options="{'subsections': True}" ${fieldAttrs}>
                <list ${listAttrs}>
                    <field name="sequence" widget="handle"/>
                    <field name="display_type" column_invisible="1"/>
                    ${columns}
                </list>
            </field>
        </form>
    `;
}

const PLAIN_COLUMNS = `
    <field name="product"/>
    <field name="name"/>
    <field name="price_subtotal"/>
`;

describe("section and note rows cover the header grid", () => {
    const configs = {
        "editable, delete allowed": { columns: PLAIN_COLUMNS },
        "editable, delete refused": {
            columns: PLAIN_COLUMNS,
            listAttrs: 'editable="bottom" delete="0"',
        },
        "readonly field": { columns: PLAIN_COLUMNS, fieldAttrs: 'readonly="1"' },
        "readonly field with an optional column": {
            columns: `${PLAIN_COLUMNS}<field name="lead" optional="show"/>`,
            fieldAttrs: 'readonly="1"',
        },
        "editable with an optional column": {
            columns: `${PLAIN_COLUMNS}<field name="lead" optional="show"/>`,
        },
        "not editable (opens a dialog)": { columns: PLAIN_COLUMNS, listAttrs: "" },
        "aggregated columns with a plain column between them": {
            columns: `
                <field name="name"/>
                <field name="price_subtotal"/>
                <field name="tax_amount"/>
                <field name="price_total"/>
            `,
            fieldAttrs: 'aggregated_fields="price_subtotal,price_total"',
        },
        "aggregated columns followed by a plain column": {
            columns: `
                <field name="product"/>
                <field name="name"/>
                <field name="price_subtotal"/>
                <field name="price_total"/>
                <field name="lead" optional="show"/>
            `,
            fieldAttrs: 'aggregated_fields="price_subtotal,price_total"',
        },
        "aggregated column before the title": {
            columns: `
                <field name="price_subtotal"/>
                <field name="product"/>
                <field name="name"/>
                <field name="lead"/>
            `,
            fieldAttrs: 'aggregated_fields="price_subtotal"',
        },
    };
    for (const [label, config] of Object.entries(configs)) {
        test(label, async () => {
            await mountView({
                type: "form",
                resModel: "columns_invoice",
                resId: 1,
                arch: invoiceArch(config),
            });
            expectRowsCoverHeaderGrid();
        });
    }

    test("title column hidden by its optional toggle", async () => {
        await mountView({
            type: "form",
            resModel: "columns_invoice",
            resId: 1,
            arch: invoiceArch({
                columns: `
                    <field name="product"/>
                    <field name="name" optional="hide"/>
                    <field name="price_subtotal"/>
                `,
                fieldAttrs: 'aggregated_fields="price_subtotal"',
            }),
        });
        expect(".o_list_table thead th[data-name=name]").toHaveCount(0);
        expect(
            queryAll(".o_data_row td[name=name]").map((td) => td.textContent),
        ).toEqual(["A", "Aa", "a note"]);
        expectRowsCoverHeaderGrid();
    });

    test("debug mode, delete refused, no optional column", async () => {
        serverState.debug = "1";
        await mountView({
            type: "form",
            resModel: "columns_invoice",
            resId: 1,
            arch: invoiceArch({
                columns: PLAIN_COLUMNS,
                listAttrs: 'editable="bottom" delete="0"',
            }),
        });
        expectRowsCoverHeaderGrid();
    });
});

const MERGE_ARCH = (listAttrs) => `
    <form>
        <field name="wizard_line_ids" widget="account_merge_wizard_lines_one2many">
            <list ${listAttrs}>
                <field name="is_selected" nolabel="1"
                       invisible="display_type == 'line_section'"/>
                <field name="account"/>
                <field name="companies"/>
                <field name="info"/>
                <field name="sequence" column_invisible="1"/>
                <field name="display_type" column_invisible="1"/>
            </list>
        </field>
    </form>
`;

describe("merge wizard rows cover the header grid", () => {
    test("as the wizard declares it", async () => {
        await mountView({
            type: "form",
            resModel: "columns_merge_wizard",
            resId: 1,
            arch: MERGE_ARCH('editable="bottom" create="0" delete="0"'),
        });
        expectRowsCoverHeaderGrid();
    });

    test("delete allowed", async () => {
        await mountView({
            type: "form",
            resModel: "columns_merge_wizard",
            resId: 1,
            arch: MERGE_ARCH('editable="bottom" create="0"'),
        });
        expectRowsCoverHeaderGrid();
    });

    test("title before the kept checkbox column", async () => {
        await mountView({
            type: "form",
            resModel: "columns_merge_wizard",
            resId: 1,
            arch: `
                <form>
                    <field name="wizard_line_ids" widget="account_merge_wizard_lines_one2many">
                        <list editable="bottom" create="0">
                            <field name="info"/>
                            <field name="account"/>
                            <field name="is_selected" nolabel="1"
                                   invisible="display_type == 'line_section'"/>
                            <field name="companies"/>
                            <field name="display_type" column_invisible="1"/>
                        </list>
                    </field>
                </form>
            `,
        });
        expectRowsCoverHeaderGrid();
    });
});
