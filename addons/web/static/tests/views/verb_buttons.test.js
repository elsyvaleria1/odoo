// @ts-check

// A button that runs a verb the user holds on some records only comes from
// the server with invisible="__verbs and not __verbs.get('<verb>')" and a
// hidden __verbs field, which the record's read answers as {verb: held}.
// Nothing here is verb-specific on the client: these tests hold that the
// ordinary view machinery evaluates that condition per record.

import { expect, test } from "@odoo/hoot";
import {
    defineModels,
    fields,
    models,
    mountView,
} from "@web/../tests/web_test_helpers";

class Document extends models.Model {
    _name = "document";
    name = fields.Char();
    __verbs = fields.Json();
    _records = [
        { id: 1, name: "mine", __verbs: { post: true, retire: false } },
        { id: 2, name: "theirs", __verbs: { post: false, retire: false } },
    ];
}

defineModels([Document]);

const POST = `<button name="action_post" type="object" string="Post"
    invisible="__verbs and not __verbs.get('post')"/>`;

test("a form offers the verb's button on a record that grants the verb", async () => {
    await mountView({
        type: "form",
        resModel: "document",
        resId: 1,
        arch: `<form><header>${POST}</header>
            <field name="name"/><field name="__verbs" invisible="1"/></form>`,
    });
    expect("button[name=action_post]").toHaveCount(1);
});

test("a form hides the verb's button on a record that does not", async () => {
    await mountView({
        type: "form",
        resModel: "document",
        resId: 2,
        arch: `<form><header>${POST}</header>
            <field name="name"/><field name="__verbs" invisible="1"/></form>`,
    });
    expect("button[name=action_post]").toHaveCount(0);
});

test("a new record, which grants nothing yet, keeps the button", async () => {
    await mountView({
        type: "form",
        resModel: "document",
        arch: `<form><header>${POST}</header>
            <field name="name"/><field name="__verbs" invisible="1"/></form>`,
    });
    expect("button[name=action_post]").toHaveCount(1);
});

test("a list shows the verb's button on the rows that grant it", async () => {
    await mountView({
        type: "list",
        resModel: "document",
        arch: `<list><field name="name"/>${POST}
            <field name="__verbs" column_invisible="1"/></list>`,
    });
    expect(".o_data_row").toHaveCount(2);
    expect(".o_data_row:eq(0) button[name=action_post]").toHaveCount(1);
    expect(".o_data_row:eq(1) button[name=action_post]").toHaveCount(0);
});
