// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import {
    Command,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { RelationalModel } from "@web/model/relational_model/relational_model";

describe.current.tags("desktop");

class Partner extends models.Model {
    name = fields.Char();
    turtles = fields.One2many({ relation: "turtle", relation_field: "turtle_trululu" });
    tags = fields.Many2many({ relation: "tag" });
    _records = [{ id: 1, name: "first", turtles: [2], tags: [1] }];
}

class Tag extends models.Model {
    name = fields.Char();
    _records = [
        { id: 1, name: "a" },
        { id: 2, name: "b" },
    ];
}

class Turtle extends models.Model {
    name = fields.Char();
    turtle_trululu = fields.Many2one({ relation: "partner" });
    _records = [{ id: 2, name: "t2" }];
}

defineModels([Partner, Turtle, Tag]);

const ARCH = `
    <form>
        <field name="name"/>
        <field name="turtles">
            <list><field name="name"/></list>
        </field>
    </form>`;

function captureModel() {
    const box = {};
    patchWithCleanup(RelationalModel.prototype, {
        setup() {
            super.setup(...arguments);
            box.model = this;
        },
    });
    return box;
}

function seedLineOnCreate() {
    patchWithCleanup(Partner.prototype, {
        onchange() {
            const res = super.onchange(...arguments);
            res.value = res.value || {};
            res.value.turtles = [Command.create({ name: "auto line" })];
            return res;
        },
    });
}

describe("reload:false save re-baselines its x2many lists", () => {
    test("editing a just-saved line writes an UPDATE, not a second CREATE", async () => {
        const box = captureModel();
        seedLineOnCreate();
        const saves = [];
        onRpc("partner", "web_save", ({ args }) => {
            saves.push(JSON.parse(JSON.stringify(args[1])));
        });
        await mountView({ type: "form", resModel: "partner", arch: ARCH });

        const record = box.model.root;
        const list = record.data.turtles;
        expect(list._commands.length).toBe(1);

        await record.update({ name: "hello" });
        await record.save({ reload: false });

        expect(list._commands).toEqual([]);
        expect(list._initialCommands).toEqual([]);
        expect(list.config.resIds.length).toBe(1);
        const line = list.records[0];
        expect(typeof line.resId).toBe("number");
        expect(line.virtualId).toBe(false);
        expect(list._currentIds).toEqual([line.resId]);

        await line.update({ name: "renamed" });
        await record.save({ reload: false });

        expect(saves.length).toBe(2);
        const commands = saves[1].turtles;
        expect(commands.length).toBe(1);
        expect(commands[0][0]).toBe(1);
        expect(commands[0][1]).toBe(line.resId);
        expect(commands[0][2]).toEqual({ name: "renamed" });
    });

    test("a discard after the save does not resurrect the seeded row", async () => {
        const box = captureModel();
        seedLineOnCreate();
        await mountView({ type: "form", resModel: "partner", arch: ARCH });

        const record = box.model.root;
        const list = record.data.turtles;
        await record.update({ name: "hello" });
        await record.save({ reload: false });
        const savedIds = [...list._currentIds];

        await record.update({ name: "hello again" });
        await record.discard();
        await list._commandsPromise;

        expect(list._currentIds).toEqual(savedIds);
        expect(list._commands).toEqual([]);
        expect(list.records.length).toBe(1);
    });

    test("a save touching no relation still sends an empty specification", async () => {
        const box = captureModel();
        const specs = [];
        onRpc("partner", "web_save", ({ kwargs }) => {
            specs.push(kwargs.specification);
        });
        await mountView({
            type: "form",
            resModel: "partner",
            resId: 1,
            arch: ARCH,
        });

        await box.model.root.update({ name: "renamed" });
        await box.model.root.save({ reload: false });

        expect(specs).toEqual([{}]);
    });
});

describe("reload:false save commits the rows it sent", () => {
    test("an edited line is clean after the save and is not sent again", async () => {
        const box = captureModel();
        const saves = [];
        onRpc("partner", "web_save", ({ args }) => {
            saves.push(JSON.parse(JSON.stringify(args[1])));
        });
        await mountView({ type: "form", resModel: "partner", resId: 1, arch: ARCH });

        const record = box.model.root;
        const line = record.data.turtles.records[0];
        await line.update({ name: "renamed" });
        await record.save({ reload: false });

        expect(line.hasPendingChanges).toBe(false);
        expect(line.savedData.name).toBe("renamed");

        await record.update({ name: "second" });
        await record.save({ reload: false });
        expect(saves).toEqual([
            { turtles: [[1, 2, { name: "renamed" }]] },
            { name: "second" },
        ]);
    });

    test("a discard after the save keeps the saved line value", async () => {
        const box = captureModel();
        await mountView({ type: "form", resModel: "partner", resId: 1, arch: ARCH });

        const record = box.model.root;
        const line = record.data.turtles.records[0];
        await line.update({ name: "renamed" });
        await record.save({ reload: false });
        await line.update({ name: "unsaved" });
        await record.discard();

        expect(record.data.turtles.records[0].data.name).toBe("renamed");
    });

    test("a reload shows a server-side unlink of a tag linked by the save", async () => {
        const box = captureModel();
        await mountView({
            type: "form",
            resModel: "partner",
            resId: 1,
            arch: `<form><field name="tags" widget="many2many_tags"/></form>`,
        });

        const record = box.model.root;
        await record.data.tags.linkTo(2);
        await record.save({ reload: false });
        expect(record.data.tags.currentIds).toEqual([1, 2]);

        await box.model.orm.write("partner", [1], { tags: [[3, 2]] });
        await record.load();

        expect(record.data.tags.currentIds).toEqual([1]);
    });

    test("a row added past the limit stays visible after the save and a discard", async () => {
        const box = captureModel();
        await mountView({
            type: "form",
            resModel: "partner",
            resId: 1,
            arch: `
                <form>
                    <field name="name"/>
                    <field name="turtles">
                        <list limit="1" editable="bottom"><field name="name"/></list>
                    </field>
                </form>`,
        });

        const record = box.model.root;
        const list = record.data.turtles;
        const added = await list.addNewRecord({ position: "bottom" });
        await added.update({ name: "added" });
        expect(list.limit).toBe(2);

        await record.save({ reload: false });
        expect(list.limit).toBe(2);
        expect(list.records.map((r) => r.data.name)).toEqual(["t2", "added"]);

        await record.update({ name: "unsaved" });
        await record.discard();
        expect(list.limit).toBe(2);
        expect(list.records.map((r) => r.data.name)).toEqual(["t2", "added"]);
    });
});
