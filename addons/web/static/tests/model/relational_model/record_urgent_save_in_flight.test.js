// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, Deferred, mockSendBeacon } from "@odoo/hoot-mock";
import {
    contains,
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
    _records = [{ id: 1, name: "first", turtles: [2] }];
}

class Turtle extends models.Model {
    name = fields.Char();
    turtle_trululu = fields.Many2one({ relation: "partner" });
    _records = [{ id: 2, name: "t2" }];
}

defineModels([Partner, Turtle]);

const LINES_ARCH = `
    <form>
        <field name="name"/>
        <field name="turtles">
            <list editable="bottom"><field name="name"/></list>
        </field>
    </form>`;

function captureModel() {
    /** @type {{ model?: any }} */
    const box = {};
    patchWithCleanup(RelationalModel.prototype, {
        setup() {
            super.setup(...arguments);
            box.model = this;
        },
    });
    return box;
}

test("an urgent save during an in-flight save flushes the input, keeps it, and asks to stay", async () => {
    const box = captureModel();
    let beacons = 0;
    mockSendBeacon(() => {
        beacons++;
        return true;
    });
    const def = new Deferred();
    /** @type {any[]} */
    const saves = [];
    onRpc("partner", "web_save", async ({ args }) => {
        saves.push(args[1]);
        await def;
    });
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });
    const record = box.model.root;

    await contains(".o_field_widget[name=name] input").edit("saved");
    const saveProm = record.save();
    await animationFrame();
    expect(record.saveState.isInFlight).toBe(true);

    await contains(".o_field_widget[name=name] input").edit("late", { confirm: false });
    expect(await record.urgentSave()).toBe(false);
    expect(beacons).toBe(0);
    expect(record.data.name).toBe("late");

    def.resolve();
    await saveProm;
    await animationFrame();

    expect(saves).toEqual([{ name: "saved" }]);
    expect(record.data.name).toBe("late");
    expect(record.dirty).toBe(true);
    expect(".o_field_widget[name=name] input").toHaveValue("late");
});

test("an urgent save during an in-flight save with nothing new lets the page go", async () => {
    const box = captureModel();
    const def = new Deferred();
    onRpc("partner", "web_save", async () => {
        await def;
    });
    await mountView({
        type: "form",
        resModel: "partner",
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });
    const record = box.model.root;

    await contains(".o_field_widget[name=name] input").edit("saved");
    const saveProm = record.save();
    await animationFrame();

    expect(await record.urgentSave()).toBe(true);

    def.resolve();
    await saveProm;
    expect(record.data.name).toBe("saved");
    expect(record.dirty).toBe(false);
});

/**
 * @param {{ reload: boolean, lineSent: boolean }} params
 */
async function editLineDuringSave({ reload, lineSent }) {
    const box = captureModel();
    const def = new Deferred();
    /** @type {any[]} */
    const saves = [];
    onRpc("partner", "web_save", async ({ args }) => {
        saves.push(JSON.parse(JSON.stringify(args[1])));
        await def;
    });
    await mountView({ type: "form", resModel: "partner", resId: 1, arch: LINES_ARCH });
    const record = box.model.root;
    if (!lineSent) {
        await contains(".o_field_widget[name=name] input").edit("parent");
    }
    await contains(".o_data_row .o_data_cell").click();
    if (lineSent) {
        await contains(".o_data_row .o_field_widget[name=name] input").edit("sent", {
            confirm: false,
        });
    }
    const saveProm = record.save({ reload });
    await animationFrame();
    expect(record.saveState.isInFlight).toBe(true);
    await contains(".o_data_row .o_field_widget[name=name] input").edit("late", {
        confirm: false,
    });
    const urgent = await record.urgentSave();
    def.resolve();
    await saveProm;
    await animationFrame();
    await record.save({ reload: false });
    return { urgent, saves };
}

for (const reload of [true, false]) {
    test(`a line edited during an in-flight save (reload=${reload}) asks to stay`, async () => {
        const { urgent } = await editLineDuringSave({ reload, lineSent: true });
        expect(urgent).toBe(false);
    });

    test(`a line first edited during an in-flight save (reload=${reload}) is sent next`, async () => {
        expect(await editLineDuringSave({ reload, lineSent: false })).toEqual({
            urgent: false,
            saves: [{ name: "parent" }, { turtles: [[1, 2, { name: "late" }]] }],
        });
    });
}

test("a line edited again during an in-flight reload:false save is sent next", async () => {
    const { saves } = await editLineDuringSave({ reload: false, lineSent: true });
    expect(saves).toEqual([
        { turtles: [[1, 2, { name: "sent" }]] },
        { turtles: [[1, 2, { name: "late" }]] },
    ]);
});
