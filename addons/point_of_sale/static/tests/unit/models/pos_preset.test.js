import { expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import {
    dateSettings,
    dateTime,
    serializeDateTime,
    toISO,
    toISODate,
} from "@web/core/l10n/dates";

import { definePosModels } from "../data/generate_model_definitions.js";
import { setupPosEnv } from "../utils.js";

definePosModels();

test("generateSlots", async () => {
    const store = await setupPosEnv();
    const presetIn = store.models["pos.preset"].get(1);
    for (const key in presetIn.availabilities) {
        expect(Array.isArray(presetIn.availabilities[key])).toBe(false);
        expect(Object.keys(presetIn.availabilities[key]).length).toBe(0);
    }
    const presetOut = store.models["pos.preset"].get(2);
    let daysWithSlot = 0;
    for (const key in presetOut.availabilities) {
        if (Object.keys(presetOut.availabilities[key]).length > 0) {
            daysWithSlot++;
            expect(Object.keys(presetOut.availabilities[key]).length).toBe(23);
        }
    }
    expect(daysWithSlot).toBe(5);
});

test("slotsUsage keys local orders by SQL datetime, not the DateTime's ISO string", async () => {
    const store = await setupPosEnv();
    const preset = store.models["pos.preset"].get(2);
    const presetTime = dateTime({
        year: 2026,
        month: 7,
        day: 17,
        hour: 12,
        minute: 20,
        second: 0,
    });
    const order = store.models["pos.order"].create({
        preset_id: preset,
        preset_time: presetTime,
    });

    const usage = preset.slotsUsage;
    const sqlKey = serializeDateTime(presetTime);
    expect(usage[sqlKey]).toEqual([order.id]);
    expect(Object.keys(usage)).toEqual([sqlKey]);
    expect(usage[toISO(presetTime)]).toBe(undefined);
});

test("slot keys are the server's serialization whatever the numbering system", async () => {
    const store = await setupPosEnv();
    patchWithCleanup(dateSettings, { numberingSystem: "arab" });
    const preset = store.models["pos.preset"].get(2);
    preset.slots_per_interval = 2;
    preset.computeAvailabilities({});
    const [date, slots] = Object.entries(preset.availabilities).find(
        ([, daySlots]) => Object.keys(daySlots).length,
    );
    const [key, slot] = Object.entries(slots)[0];
    expect(date).toBe(toISODate(slot.datetime));
    expect(key).toBe(serializeDateTime(slot.datetime));

    const order = store.models["pos.order"].create({
        preset_id: preset,
        preset_time: slot.datetime,
    });
    preset.computeAvailabilities({ [key]: [9001] });
    const booked = preset.availabilities[date][key];
    expect([...booked.order_ids]).toEqual([order.id, 9001]);
    expect(booked.isFull).toBe(true);
});

test("slotsUsage skips orders without a preset_time", async () => {
    const store = await setupPosEnv();
    const preset = store.models["pos.preset"].get(2);
    store.models["pos.order"].create({ preset_id: preset });
    expect(preset.slotsUsage).toEqual({});
});
