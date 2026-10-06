import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { expectRowsCoverHeaderGrid } from "@web/../tests/views/list/list_grid_test_helpers";
import {
    defineModels,
    fields,
    models,
    mountView,
    serverState,
} from "@web/../tests/web_test_helpers";

class PurchaseOrder extends models.Model {
    _name = "purchase.order";

    name = fields.Char({ string: "Reference" });
    state = fields.Char();
    amount_total = fields.Float();
    alternative_po_ids = fields.Many2many({ relation: "purchase.order" });

    _records = [
        {
            id: 1,
            name: "P00001",
            state: "draft",
            amount_total: 10,
            alternative_po_ids: [1, 2, 3],
        },
        {
            id: 2,
            name: "P00002",
            state: "draft",
            amount_total: 20,
            alternative_po_ids: [1, 2, 3],
        },
        {
            id: 3,
            name: "P00003",
            state: "draft",
            amount_total: 30,
            alternative_po_ids: [1, 2, 3],
        },
    ];
}

defineModels([PurchaseOrder]);
defineMailModels();

const arch = ({ fieldAttrs = "", listAttrs = "", optional = "" } = {}) => `
    <form>
        <field name="alternative_po_ids" widget="many2many_alt_pos" ${fieldAttrs}>
            <list ${listAttrs}>
                <field name="name"/>
                <field name="amount_total"/>
                <field name="state" ${optional}/>
            </list>
        </field>
    </form>
`;

describe("alternative order rows cover the header grid", () => {
    const configs = {
        "as the order form declares it": {},
        "an optional column": { optional: 'optional="show"' },
        "readonly field": { fieldAttrs: 'readonly="1"' },
        "readonly field with an optional column": {
            fieldAttrs: 'readonly="1"',
            optional: 'optional="hide"',
        },
        "debug, delete refused": { listAttrs: 'delete="0"', debug: true },
    };
    for (const [label, { debug, ...config }] of Object.entries(configs)) {
        test(label, async () => {
            if (debug) {
                serverState.debug = "1";
            }
            await mountView({
                type: "form",
                resModel: "purchase.order",
                resId: 1,
                arch: arch(config),
            });
            expectRowsCoverHeaderGrid();
        });
    }
});

test("only the other orders can be unlinked from the current one", async () => {
    await mountView({
        type: "form",
        resModel: "purchase.order",
        resId: 1,
        arch: arch(),
    });
    expect(".o_data_row").toHaveCount(3);
    expect(".o_data_row:eq(0) button[name=delete]").toHaveCount(0);
    expect(".o_data_row:eq(1) button[name=delete]").toHaveCount(1);
    expect(".o_data_row:eq(2) button[name=delete]").toHaveCount(1);
});
