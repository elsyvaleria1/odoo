import { SectionAndNoteListRenderer } from "@account/components/section_and_note_fields_backend/section_and_note_fields_backend";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-dom";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

class InvoiceLine extends models.Model {
    _name = "invoice_line";
    _records = [
        { id: 1, name: "sec1", display_type: "line_section", sequence: 1 },
        { id: 2, name: "sec1-r1", display_type: false, sequence: 2 },
        { id: 3, name: "sec1-sub1", display_type: "line_subsection", sequence: 3 },
        { id: 4, name: "sec1-sub1-r1", display_type: false, sequence: 4 },
        { id: 5, name: "sec2", display_type: "line_section", sequence: 5 },
        { id: 6, name: "sec2-r1", display_type: false, sequence: 6 },
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
    invoice_id = fields.Many2one({ relation: "invoice" });
    sequence = fields.Integer();
    collapse_composition = fields.Boolean({ default: false });
    collapse_prices = fields.Boolean({ default: false });
}

class Invoice extends models.Model {
    _records = [{ id: 1, invoice_line_ids: [1, 2, 3, 4, 5, 6] }];

    invoice_line_ids = fields.One2many({ relation: "invoice_line" });
}

defineModels([Invoice, InvoiceLine]);
defineMailModels();

onRpc("has_group", () => true);

const ARCH = `
    <form>
        <field
            name="invoice_line_ids"
            widget="section_and_note_one2many"
            options="{'subsections': True, 'hide_composition': True, 'hide_prices': True}"
        >
            <list editable="bottom">
                <control>
                    <create name="add_line_control" string="Add a line"/>
                    <create name="add_section_control" string="Add a section" context="{'default_display_type': 'line_section'}"/>
                </control>
                <field name="sequence" widget="handle"/>
                <field name="name"/>
                <field name="display_type" column_invisible="1"/>
                <field name="collapse_composition" column_invisible="1"/>
                <field name="collapse_prices" column_invisible="1"/>
            </list>
        </field>
    </form>`;

function countParentSectionMaps() {
    const counter = { maps: 0 };
    patchWithCleanup(SectionAndNoteListRenderer.prototype, {
        setup() {
            super.setup();
            const read = this.parentSections;
            const seen = new WeakSet();
            this.parentSections = () => {
                const map = read();
                if (!seen.has(map)) {
                    seen.add(map);
                    counter.maps++;
                }
                return map;
            };
        },
    });
    return counter;
}

test("the parent sections are derived once, however many rows read them", async () => {
    const counter = countParentSectionMaps();
    await mountView({ type: "form", resModel: "invoice", resId: 1, arch: ARCH });
    await animationFrame();

    expect(".o_data_row").toHaveCount(6);
    expect(counter.maps).toBe(1);
});

test("editing a line's name leaves the parent sections alone", async () => {
    const counter = countParentSectionMaps();
    await mountView({ type: "form", resModel: "invoice", resId: 1, arch: ARCH });
    await animationFrame();
    await contains(".o_data_row:contains(sec2-r1) .o_data_cell[name=name]").click();
    counter.maps = 0;

    await contains(".o_selected_row [name=name] input").edit("renamed", {
        confirm: "blur",
    });
    await animationFrame();

    expect(".o_data_row").toHaveCount(6);
    expect(".o_data_row:contains(renamed)").not.toHaveClass("text-muted");
    expect(counter.maps).toBe(0);
});

test("collapsing a section mutes its lines without deriving the parents again", async () => {
    const counter = countParentSectionMaps();
    await mountView({ type: "form", resModel: "invoice", resId: 1, arch: ARCH });
    await animationFrame();
    counter.maps = 0;
    expect(".o_data_row.text-muted").toHaveCount(0);

    await contains(".o_data_row:contains(sec1) .o_list_section_options button").click();
    await contains(".o-dropdown-item:contains(Hide Composition)").click();
    await animationFrame();

    expect(".o_data_row:contains(sec1-r1)").toHaveClass("text-muted");
    expect(".o_data_row:contains(sec1-sub1-r1)").toHaveClass("text-muted");
    expect(".o_data_row:contains(sec2-r1)").not.toHaveClass("text-muted");
    expect(counter.maps).toBe(0);
});

test("a new line joins the last section, and the parents are derived again", async () => {
    const counter = countParentSectionMaps();
    await mountView({ type: "form", resModel: "invoice", resId: 1, arch: ARCH });
    await animationFrame();
    await contains(".o_data_row:contains(sec2) .o_list_section_options button").click();
    await contains(".o-dropdown-item:contains(Hide Composition)").click();
    await animationFrame();
    counter.maps = 0;

    await contains(".o_field_x2many_list_row_add a:contains(Add a line)").click();
    await contains(".o_selected_row [name=name] input").edit("sec2-r2", {
        confirm: "blur",
    });
    await animationFrame();

    expect(".o_data_row").toHaveCount(7);
    expect(".o_data_row:contains(sec2-r2)").toHaveClass("text-muted");
    expect(".o_data_row:contains(sec1-r1)").not.toHaveClass("text-muted");
    expect(counter.maps).toBe(1);
});

test("inserting into an earlier section derives parents for insertion and resequencing", async () => {
    const counter = countParentSectionMaps();
    await mountView({ type: "form", resModel: "invoice", resId: 1, arch: ARCH });
    await animationFrame();
    counter.maps = 0;

    await contains(".o_data_row:contains(sec1) .o_list_section_options button").click();
    await contains(".o-dropdown-item:contains(Add a line)").click();
    await contains(".o_selected_row [name=name] input").edit("sec1-r2", {
        confirm: "blur",
    });
    await animationFrame();

    expect(".o_data_row").toHaveCount(7);
    expect(counter.maps).toBe(2);
});

test("confirming a new line with Enter re-derives only for the second new line", async () => {
    const counter = countParentSectionMaps();
    await mountView({ type: "form", resModel: "invoice", resId: 1, arch: ARCH });
    await animationFrame();
    counter.maps = 0;

    await contains(".o_field_x2many_list_row_add a:contains(Add a line)").click();
    await contains(".o_selected_row [name=name] input").edit("sec2-r2", {
        confirm: "enter",
    });
    await animationFrame();

    expect(".o_data_row").toHaveCount(8);
    expect(counter.maps).toBe(2);
});
