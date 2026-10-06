// @ts-check

import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { toRaw } from "@odoo/owl";
import {
    defineModels,
    defineWebModels,
    fields,
    MockServer,
    models,
    mountView,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { RelationalRecord } from "@web/model/relational_model/record";
import { RelationalModel } from "@web/model/relational_model/relational_model";
import { StaticList } from "@web/model/relational_model/static_list";

class Partner extends models.Model {
    name = fields.Char();
    tag_ids = fields.Many2many({ relation: "tag" });
    line_ids = fields.One2many({ relation: "line", relation_field: "partner_id" });
    _records = [{ id: 1, name: "p", tag_ids: [1, 2], line_ids: [1] }];
}
class Tag extends models.Model {
    name = fields.Char();
    _records = [
        { id: 1, name: "t1" },
        { id: 2, name: "t2" },
    ];
}
class Line extends models.Model {
    name = fields.Char();
    partner_id = fields.Many2one({ relation: "partner" });
    tag_ids = fields.Many2many({ relation: "tag" });
    other_tag_ids = fields.Many2many({ relation: "tag" });
    _records = [{ id: 1, name: "l1", partner_id: 1, tag_ids: [1], other_tag_ids: [2] }];
}
defineWebModels();
defineModels([Partner, Tag, Line]);

const ARCH = `
    <form>
        <field name="name"/>
        <field name="tag_ids" widget="many2many_tags"/>
        <field name="line_ids">
            <list editable="bottom"><field name="name"/></list>
        </field>
    </form>`;

/** @returns {Promise<RelationalModel>} */
async function mountFormAndGetModel(arch = ARCH) {
    /** @type {RelationalModel[]} */
    const instances = [];
    patchWithCleanup(RelationalModel.prototype, {
        setup(/** @type {any[]} */ ...args) {
            super.setup(...args);
            instances.push(/** @type {any} */ (this));
        },
    });
    await mountView({ resModel: "partner", type: "form", resId: 1, arch });
    return /** @type {RelationalModel} */ (instances.at(-1));
}

test("a reload keeps an x2many the server sent unchanged, and writes in place the row that reads differently", async () => {
    const model = await mountFormAndGetModel();
    const { tag_ids: tagsBefore, line_ids: linesBefore } = model.root.data;
    const dataBefore = model.root.data;
    const [renamed, untouched] = tagsBefore.records;

    await model.root.load();
    expect(model.root.data).toBe(dataBefore);
    expect(model.root.data.tag_ids).toBe(tagsBefore);
    expect(model.root.data.line_ids).toBe(linesBefore);

    /** @type {any[]} */
    const reloaded = [];
    /** @type {any[]} */
    const refreshed = [];
    patchWithCleanup(RelationalRecord.prototype, {
        setData(/** @type {any[]} */ ...args) {
            reloaded.push(`${this.resModel},${this.resId}`);
            return super.setData(...args);
        },
        refreshFields(/** @type {any} */ row, /** @type {string[]} */ fieldNames) {
            refreshed.push(`${this.resModel},${this.resId}: ${fieldNames}`);
            return super.refreshFields(row, fieldNames);
        },
    });
    MockServer.env["tag"].write([1], { name: "t1-renamed" });
    await model.root.load();
    await animationFrame();
    expect(model.root.data.tag_ids).toBe(tagsBefore);
    expect(model.root.data.tag_ids.records).toEqual([renamed, untouched]);
    expect(renamed.data.display_name).toBe("t1-renamed");
    expect(reloaded).toEqual(["partner,1"]);
    expect(refreshed).toEqual(["tag,1: display_name"]);
    expect(model.root.data.line_ids).toBe(linesBefore);
    expect(".o_field_many2many_tags .o_tag:first").toHaveText("t1-renamed");
});

test("a reload rebuilds an x2many whose rows are not the ones it holds", async () => {
    const model = await mountFormAndGetModel();
    const record = model.root;

    const before = record.data.tag_ids;
    MockServer.env["partner"].write([1], { tag_ids: [2, 1] });
    await record.load();
    expect(record.data.tag_ids).not.toBe(before);
    expect(record.data.tag_ids.records.map((tag) => tag.resId)).toEqual([2, 1]);

    const reordered = record.data.tag_ids;
    MockServer.env["partner"].write([1], { tag_ids: [2] });
    await record.load();
    expect(record.data.tag_ids).not.toBe(reordered);
    expect(record.data.tag_ids.records.map((tag) => tag.resId)).toEqual([2]);
});

test("a refresh that keeps the user's changes is a reload in place when there are none", async () => {
    const model = await mountFormAndGetModel();
    const record = model.root;
    const { data, line_ids: lines } = { data: record.data, ...record.data };
    const [line] = lines.records;
    const read = () =>
        MockServer.env["partner"].web_read([1], {
            name: {},
            tag_ids: { fields: { display_name: {} } },
            line_ids: { fields: { name: {} } },
        })[0];

    MockServer.env["line"].write([1], { name: "l1-refreshed" });
    MockServer.env["partner"].write([1], { name: "p-refreshed" });
    record.setData(read(), { keepChanges: true });
    await animationFrame();
    expect(record.data).toBe(data);
    expect(record.data.name).toBe("p-refreshed");
    expect(record.data.line_ids).toBe(lines);
    expect(record.data.line_ids.records[0]).toBe(line);
    expect(line.data.name).toBe("l1-refreshed");
    expect(record.dirty).toBe(false);
    expect(".o_field_x2many .o_data_row:first").toHaveText("l1-refreshed");

    await record.update({ name: "typed by the user" });
    MockServer.env["line"].write([1], { name: "l1-again" });
    record.setData(read(), { keepChanges: true });
    expect(record.data).not.toBe(data);
    expect(record.data.name).toBe("typed by the user");
    expect(record.data.line_ids.records[0].data.name).toBe("l1-again");
});

test("a sorted x2many is rebuilt when the value it is sorted on changes", async () => {
    const model = await mountFormAndGetModel();
    const record = model.root;
    MockServer.env["line"].create({ name: "l2", partner_id: 1 });
    await record.load();
    await record.data.line_ids.sortBy("name");
    const sorted = record.data.line_ids;
    expect(sorted.orderBy.map((term) => term.name)).toEqual(["name"]);

    MockServer.env["line"].write([1], { name: "z-last" });
    await record.load();
    expect(record.data.line_ids).not.toBe(sorted);
});

test("a reload rebuilds an x2many that carries a staged command or an edited row", async () => {
    const model = await mountFormAndGetModel();
    const record = model.root;

    const withCommand = record.data.line_ids;
    await withCommand.addNewRecord({ position: "bottom" });
    expect(withCommand.hasStagedCommands).toBe(true);
    await record.load();
    expect(record.data.line_ids).not.toBe(withCommand);
    expect(record.data.line_ids.records).toHaveLength(1);

    const withEdit = record.data.line_ids;
    await withEdit.records[0].update({ name: "l1-edited" });
    expect(withEdit.records[0].hasPendingChanges).toBe(true);
    await record.load();
    expect(record.data.line_ids).not.toBe(withEdit);
    expect(record.data.line_ids.records[0].data.name).toBe("l1");
});

test("a refresh writes alone the fields of a line that read differently, and what reads them", async () => {
    const model = await mountFormAndGetModel(`
        <form>
            <field name="name"/>
            <field name="line_ids">
                <list editable="bottom">
                    <field name="name"/>
                    <field name="tag_ids" widget="many2many_tags" context="{'line_name': name}"/>
                    <field name="other_tag_ids" widget="many2many_tags" context="{'fixed': 1}"/>
                </list>
            </field>
        </form>`);
    const record = model.root;
    const [line] = record.data.line_ids.records;
    const named = toRaw(line.data.tag_ids);
    const fixed = toRaw(line.data.other_tag_ids);
    expect(named.context.line_name).toBe("l1");

    /** @type {string[]} */
    const reparsed = [];
    /** @type {string[]} */
    const recontexted = [];
    patchWithCleanup(RelationalRecord.prototype, {
        setData(/** @type {any[]} */ ...args) {
            reparsed.push(`${this.resModel},${this.resId}`);
            return super.setData(...args);
        },
    });
    patchWithCleanup(StaticList.prototype, {
        updateContext(/** @type {any} */ context) {
            const list = toRaw(this);
            if (list === named || list === fixed) {
                recontexted.push(list === named ? "tag_ids" : "other_tag_ids");
            }
            return super.updateContext(context);
        },
    });
    MockServer.env["line"].write([1], { name: "l1-moved" });
    await record.load();
    await animationFrame();

    expect(record.data.line_ids.records[0]).toBe(line);
    expect(line.data.name).toBe("l1-moved");
    expect(line.evalContext.name).toBe("l1-moved");
    expect(named.context.line_name).toBe("l1-moved");
    expect(recontexted).toEqual(["tag_ids"]);
    expect(reparsed).toEqual(["partner,1"]);
    expect(".o_field_x2many .o_data_row:first .o_data_cell:first").toHaveText(
        "l1-moved",
    );
});
