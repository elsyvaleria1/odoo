/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import {
    compareDates,
    now as getNow,
    serializeDateTime,
    toISODate,
} from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";

import { Base } from "./related_models/index.js";
const log = makeLogger("pos.preset");

export class PosPreset extends Base {
    static pythonModel = "pos.preset";
    static excludedLazyGetters = [
        ...Base.excludedLazyGetters,
        "nextSlot",
        "currentSlot",
        "availabilities",
        "upcomingAvailabilities",
    ];

    initState() {
        super.initState();
        this.uiState = {
            availabilities: {},
        };

        this.computeAvailabilities();
    }

    get needsSlot() {
        return this.use_timing;
    }

    get needsName() {
        return this.identification === "name";
    }

    get needsPartner() {
        return this.identification === "address";
    }

    get orders() {
        return this.models["pos.order"].filter((o) => o.preset_id?.id === this.id);
    }

    get nextSlot() {
        const dateNow = getNow();
        return Object.values(this.availabilities[toISODate(dateNow)] || {}).find(
            (s) => !s.isFull && compareDates(s.datetime, dateNow) >= 0,
        );
    }

    get availabilities() {
        const now = getNow();
        if (this.uiState.generatedFor !== `${toISODate(now)}/${now.timeZoneId}`) {
            log.logic("availabilities: stale, regenerating", () => ({
                preset: this.id,
                generatedFor: this.uiState.generatedFor,
                now: `${toISODate(now)}/${now.timeZoneId}`,
            }));
            this.computeAvailabilities(this.uiState.serverUsage, now);
        }
        return this.uiState.availabilities;
    }

    get upcomingAvailabilities() {
        const now = getNow();
        return Object.fromEntries(
            Object.entries(this.availabilities).map(([date, slots]) => [
                date,
                Object.fromEntries(
                    Object.entries(slots).filter(
                        ([, slot]) => compareDates(slot.datetime, now) >= 0,
                    ),
                ),
            ]),
        );
    }

    get slotsUsage() {
        return (
            this.orders.reduce((acc, order) => {
                if (!order.preset_time || order.state === "cancel") {
                    return acc;
                }
                const key = serializeDateTime(order.preset_time);
                if (!acc[key]) {
                    acc[key] = [];
                }
                acc[key].push(order.id);
                return acc;
            }, {}) || {}
        );
    }

    computeAvailabilities(usages = {}, now = getNow()) {
        const endCompute = log.perf("computeAvailabilities");
        this.uiState.serverUsage = usages;
        this.generateSlots(now);

        const allSlots = Object.values(this.uiState.availabilities).reduce(
            (acc, curr) => Object.assign(acc, curr),
            {},
        );

        for (const [datetime, slot] of Object.entries(allSlots)) {
            const usage = usages[datetime];
            slot.order_ids = new Set([...slot.order_ids, ...(usage || [])]);
            slot.isFull = slot.order_ids.size >= this.slots_per_interval;
        }
        endCompute({
            preset: this.id,
            slots: Object.keys(allSlots).length,
            full: Object.values(allSlots).filter((s) => s.isFull).length,
            serverUsage: Object.keys(usages || {}).length,
        });

        return this.uiState.availabilities;
    }

    get currentSlot() {
        const now = getNow();
        const interval = this.interval_time;
        const todayAvailabilities = this.availabilities[toISODate(now)] || {};
        for (const slot of Object.values(todayAvailabilities)) {
            if (
                compareDates(slot.datetime, now) <= 0 &&
                compareDates(slot.datetime.add({ minutes: interval }), now) > 0
            ) {
                return slot;
            }
        }
        return false;
    }

    generateSlots(now = getNow()) {
        const usage = this.slotsUsage;
        const interval = this.interval_time;
        const slots = {};

        for (const i of [...Array(7).keys()]) {
            const dateNow = now.add({ days: i });
            const getDateTime = (hour) =>
                dateNow
                    .startOfDay()
                    .add({ days: Math.floor(hour / 24) })
                    .with({
                        hour: Math.floor(hour) % 24,
                        minute: Math.round((hour % 1) * 60),
                    });
            const dayOfWeek = (dateNow.dayOfWeek - 1).toString();
            const date = toISODate(dateNow);
            const attToday = this.attendance_ids.filter(
                (a) => a.dayofweek === dayOfWeek,
            );
            slots[date] = {};

            for (const attendance of attToday) {
                const dateOpening = getDateTime(attendance.hour_from);
                const dateClosing = getDateTime(attendance.hour_to);

                let start = dateOpening;
                while (
                    compareDates(start, dateOpening) >= 0 &&
                    compareDates(start, dateClosing) <= 0 &&
                    interval > 0
                ) {
                    const sqlDatetime = serializeDateTime(start);

                    if (slots[date][sqlDatetime]) {
                        for (const id of usage[sqlDatetime] || []) {
                            slots[date][sqlDatetime].order_ids.add(id);
                        }
                    } else {
                        slots[date][sqlDatetime] = {
                            periode: attendance.day_period,
                            datetime: start,
                            order_ids: new Set(usage[sqlDatetime] || []),
                        };
                    }
                    start = start.add({ minutes: interval });
                }
            }
        }

        this.uiState.availabilities = slots;
        this.uiState.generatedFor = `${toISODate(now)}/${now.timeZoneId}`;
        log.lifecycle("generateSlots", () => ({
            preset: this.id,
            interval,
            days: Object.keys(slots).length,
            attendances: this.attendance_ids.length,
            localUsage: Object.keys(usage).length,
        }));
    }
}

registry.category("pos_available_models").add(PosPreset.pythonModel, PosPreset);
