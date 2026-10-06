// @ts-check

import { expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    selectFieldDropdownItem,
    serverState,
    webModels,
} from "@web/../tests/web_test_helpers";

const { ResCompany, ResPartner, ResUsers } = webModels;

class Foo extends models.Model {
    name = fields.Char();
    int_field = fields.Integer();
    trululu = fields.Many2one({ relation: "foo" });

    _records = [
        { id: 1, name: "yop", int_field: 1, trululu: 1 },
        { id: 2, name: "blip", int_field: 2, trululu: 2 },
    ];
}

defineModels([Foo, ResCompany, ResPartner, ResUsers]);

test.tags("desktop");
test("the mass-edit read-back spec resolves uid-dependent field contexts", async () => {
    /** @type {any} */
    let spec;
    onRpc("web_save", ({ kwargs }) => {
        spec = kwargs.specification;
    });

    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list multi_edit="1">
                <field name="int_field"/>
                <field name="trululu" context="{'from_uid': uid}"/>
            </list>`,
    });

    await contains(".o_data_row:eq(0) .o_list_record_selector input").click();
    await contains(".o_data_row:eq(1) .o_list_record_selector input").click();
    await contains(".o_data_row:eq(0) .o_data_cell[name='int_field']").click();
    await contains(".o_field_widget[name=int_field] input").edit("64");
    await contains(".modal .btn-primary").click();

    expect(spec).not.toBe(undefined);
    expect(spec.trululu.context).toEqual({ from_uid: serverState.userId });
});

test.tags("desktop");
test("re-picking the edited row's own many2one still writes it to the other rows", async () => {
    /** @type {any[]} */
    const saves = [];
    onRpc("web_save", ({ args }) => {
        saves.push(args.slice(0, 2));
    });

    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list multi_edit="1">
                <field name="trululu"/>
            </list>`,
    });

    await contains(".o_data_row:eq(0) .o_list_record_selector input").click();
    await contains(".o_data_row:eq(1) .o_list_record_selector input").click();
    await contains(".o_data_row:eq(0) .o_data_cell[name='trululu']").click();
    await selectFieldDropdownItem("trululu", "yop");
    expect(".modal").toHaveCount(1);
    await contains(".modal .btn-primary").click();

    expect(saves).toEqual([[[1, 2], { trululu: 1 }]]);
    expect(queryAllTexts(".o_data_cell[name='trululu']")).toEqual(["yop", "yop"]);
});

test.tags("desktop");
test("re-picking a many2one every selected row already holds writes nothing and asks nothing", async () => {
    /** @type {any[]} */
    const saves = [];
    onRpc("web_save", ({ args }) => {
        saves.push(args.slice(0, 2));
    });

    await mountView({
        resModel: "foo",
        type: "list",
        arch: `
            <list multi_edit="1">
                <field name="trululu"/>
            </list>`,
    });

    await contains(".o_data_row:eq(0) .o_list_record_selector input").click();
    await contains(".o_data_row:eq(1) .o_list_record_selector input").click();
    await contains(".o_data_row:eq(0) .o_data_cell[name='trululu']").click();
    await selectFieldDropdownItem("trululu", "blip");
    await contains(".modal .btn-primary").click();
    expect(saves).toEqual([[[1, 2], { trululu: 2 }]]);
    expect(".o_data_row .o_list_record_selector input:checked").toHaveCount(2);

    await contains(".o_data_row:eq(1) .o_data_cell[name='trululu']").click();
    await selectFieldDropdownItem("trululu", "blip");
    expect(".modal").toHaveCount(0);
    expect(saves).toHaveLength(1);
    expect(".o_data_row:eq(0) .o_data_cell[name='trululu']").toHaveText("blip");
    expect(".o_data_row:eq(1) .o_field_widget[name=trululu] input").toHaveValue("blip");
});
