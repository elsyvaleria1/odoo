// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { queryOne } from "@odoo/hoot-dom";
import { animationFrame, Deferred, mockSendBeacon } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    isPromptRequested,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { ModelEvent } from "@web/core/events";
import { MICROTASK_BUDGET } from "@web/core/utils/concurrency";
import { FormController } from "@web/views/form/form_controller";

describe.current.tags("desktop");

class Partner extends models.Model {
    name = fields.Char();
    date = fields.Date();
    timmy = fields.Many2many({ relation: "partner.type" });
    _records = [{ id: 1, name: "first", timmy: [] }];
}

class PartnerType extends models.Model {
    name = fields.Char();
    _records = [{ id: 12, name: "gold" }];
}

defineModels([Partner, PartnerType]);

test("a microtask-only unload chain is seen by the browser", async () => {
    const requested = await isPromptRequested((ev) =>
        Promise.resolve()
            .then(() => Promise.allSettled([Promise.resolve()]))
            .then(() => ev.preventDefault()),
    );
    expect(requested).toBe(true);
});

test("an unload during an in-flight save asks to stay before the browser decides", async () => {
    /** @type {{ controller?: any }} */
    const box = {};
    patchWithCleanup(FormController.prototype, {
        setup() {
            super.setup(...arguments);
            box.controller = this;
        },
    });
    mockSendBeacon(() => true);
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
    const controller = box.controller;
    controller.model.useSendBeaconToSaveUrgently = true;
    await contains(".o_field_widget[name=name] input").edit("saved");
    const saveProm = controller.saveCoordinator.requestSave();
    await animationFrame();
    expect(controller.model.root.saveState.isInFlight).toBe(true);
    await contains(".o_field_widget[name=name] input").edit("late", { confirm: false });

    const requested = await isPromptRequested((ev) => controller.beforeUnload(ev));

    def.resolve();
    await saveProm;
    expect(requested).toBe(true);
});

function captureController() {
    /** @type {{ controller?: any }} */
    const box = {};
    patchWithCleanup(FormController.prototype, {
        setup() {
            super.setup(...arguments);
            box.controller = this;
        },
    });
    return box;
}

/**
 * @param {{ arch?: string }} [params]
 * @returns {Promise<{ controller: any, blobs: Blob[] }>}
 */
async function mountBeaconForm({ arch = `<form><field name="name"/></form>` } = {}) {
    const box = captureController();
    /** @type {Blob[]} */
    const blobs = [];
    mockSendBeacon((_route, blob) => {
        blobs.push(/** @type {Blob} */ (blob));
        return true;
    });
    await mountView({ type: "form", resModel: "partner", resId: 1, arch });
    const controller = box.controller;
    controller.model.useSendBeaconToSaveUrgently = true;
    return { controller, blobs };
}

/**
 * @param {Blob[]} blobs
 * @returns {Promise<Record<string, any>[]>} the values each beacon wrote
 */
async function beaconValues(blobs) {
    const texts = await Promise.all(blobs.map((blob) => blob.text()));
    return texts.map((text) => JSON.parse(text).params.args[1]);
}

/**
 * @param {{ controller: any, blobs: Blob[] }} form
 * @param {() => void} [lastAction] done in the unload dispatch, right before it
 * @returns {Promise<{ requested: boolean, beaconsSent: number }>}
 */
async function unloadForm({ controller, blobs }, lastAction) {
    let beaconsSent = 0;
    const requested = await isPromptRequested(
        (ev) => {
            lastAction?.();
            return controller.beforeUnload(ev);
        },
        () => (beaconsSent = blobs.length),
    );
    return { requested, beaconsSent };
}

/**
 * @param {any} controller
 * @param {() => Promise<unknown>} work
 * @returns {() => void}
 */
function onUrgentFlush(controller, work) {
    /** @param {any} ev */
    const listener = (ev) => ev.detail.proms.push(work());
    controller.model.bus.addEventListener(ModelEvent.WILL_SAVE_URGENTLY, listener);
    return () =>
        controller.model.bus.removeEventListener(
            ModelEvent.WILL_SAVE_URGENTLY,
            listener,
        );
}

describe("a flush that outlives the unload dispatch", () => {
    test("a handler waiting on a timer asks to stay, and the beacon still leaves", async () => {
        const form = await mountBeaconForm();
        await contains(".o_field_widget[name=name] input").edit("typed", {
            confirm: false,
        });
        const stop = onUrgentFlush(
            form.controller,
            () => new Promise((resolve) => setTimeout(resolve, 20)),
        );

        const { requested, beaconsSent } = await unloadForm(form);
        stop();

        expect(requested).toBe(true);
        expect(beaconsSent).toBe(1);
    });

    test("a handler waiting on an RPC asks to stay, and the beacon still leaves", async () => {
        const def = new Deferred();
        onRpc("partner", "slow_check", () => def);
        const form = await mountBeaconForm();
        await contains(".o_field_widget[name=name] input").edit("typed", {
            confirm: false,
        });
        const stop = onUrgentFlush(form.controller, () =>
            form.controller.model.orm.call("partner", "slow_check", [[1]]),
        );

        const { requested, beaconsSent } = await unloadForm(form);
        stop();
        def.resolve(true);

        expect(requested).toBe(true);
        expect(beaconsSent).toBe(1);
    });

    test("an untouched record with a handler that settles at once lets the page go", async () => {
        const form = await mountBeaconForm();
        const stop = onUrgentFlush(form.controller, () => Promise.resolve());

        const { requested, beaconsSent } = await unloadForm(form);
        stop();

        expect(requested).toBe(false);
        expect(beaconsSent).toBe(0);
    });

    test("a typed value flushed in microtasks leaves by beacon without a prompt", async () => {
        const form = await mountBeaconForm();
        await contains(".o_field_widget[name=name] input").edit("typed", {
            confirm: false,
        });

        const { requested, beaconsSent } = await unloadForm(form);

        expect(requested).toBe(false);
        expect(beaconsSent).toBe(1);
        expect(await beaconValues(form.blobs)).toEqual([{ name: "typed" }]);
    });
});

test("a beacon save decides well within the microtask budget", async () => {
    const form = await mountBeaconForm({
        arch: `<form><field name="name"/><field name="date"/><field name="timmy" widget="many2many_checkboxes"/></form>`,
    });
    await contains(".o_field_widget[name=name] input").edit("typed", {
        confirm: false,
    });
    const ev = new Event("beforeunload", { cancelable: true });
    let decided = false;
    Promise.resolve(form.controller.beforeUnload(ev)).then(() => (decided = true));
    let hops = 0;
    while (!decided) {
        await Promise.resolve();
        hops++;
    }
    expect(hops).toBeLessThan(MICROTASK_BUDGET / 4);
    expect(ev.defaultPrevented).toBe(false);
});

describe("model mutex work the beacon cannot carry", () => {
    test("an update queued behind an in-flight save asks to stay", async () => {
        const def = new Deferred();
        onRpc("partner", "web_save", () => def);
        const form = await mountBeaconForm();
        const record = form.controller.model.root;
        await contains(".o_field_widget[name=name] input").edit("saved");
        const saveProm = form.controller.saveCoordinator.requestSave();
        await animationFrame();
        expect(record.saveState.isInFlight).toBe(true);
        const queued = record.update({ name: "queued" });

        const { requested } = await unloadForm(form);

        def.resolve();
        await saveProm;
        await queued;
        expect(requested).toBe(true);
        expect(record.data.name).toBe("queued");
    });

    test("an update waiting on its onchange asks to stay", async () => {
        Partner._onChanges = { name() {} };
        const def = new Deferred();
        onRpc("partner", "onchange", () => def);
        const form = await mountBeaconForm();
        const record = form.controller.model.root;
        const pending = record.update({ name: "from a button" });
        await animationFrame();

        const { requested } = await unloadForm(form);

        def.resolve();
        await pending;
        expect(requested).toBe(true);
    });
});

describe("field flushes on unload", () => {
    test("a date waiting on its onchange leaves by beacon", async () => {
        Partner._onChanges = { date() {} };
        const def = new Deferred();
        onRpc("partner", "onchange", () => def);
        const form = await mountBeaconForm({
            arch: `<form><field name="date"/></form>`,
        });
        await contains(".o_field_widget[name=date] input").edit("09/28/2026");
        await animationFrame();

        const { requested, beaconsSent } = await unloadForm(form);
        def.resolve();
        await animationFrame();

        expect(beaconsSent).toBe(1);
        expect(requested).toBe(true);
        expect(await beaconValues(form.blobs)).toEqual([{ date: "2026-09-28" }]);
    });

    test("a checkbox toggled behind a busy model leaves by beacon", async () => {
        Partner._onChanges = { name() {} };
        const def = new Deferred();
        onRpc("partner", "onchange", () => def);
        const form = await mountBeaconForm({
            arch: `<form><field name="name"/><field name="timmy" widget="many2many_checkboxes"/></form>`,
        });
        const pending = form.controller.model.root.update({ name: "from a button" });
        await animationFrame();
        const checkbox = /** @type {HTMLInputElement} */ (
            queryOne("div.o_field_widget[name=timmy] div.form-check input")
        );

        const { requested, beaconsSent } = await unloadForm(form, () =>
            checkbox.click(),
        );
        def.resolve();
        await pending;

        expect(beaconsSent).toBe(1);
        expect(requested).toBe(true);
        expect(await beaconValues(form.blobs)).toEqual([{ timmy: [[4, 12, false]] }]);
    });
});
