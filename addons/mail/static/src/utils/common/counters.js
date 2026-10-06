// @ts-check
/** @odoo-module native */
import { toRaw } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";

const log = makeLogger("mail.counters");
const MAX_LOGGED_DELTAS = 200;

/**
 * @typedef {Object} CounterLog
 * @property {number} busId the `<field>_bus_id` this log was last in sync with
 * @property {number} replayableAfter every delta with a higher bus id is in `deltas`
 * @property {{busId: number, delta: number}[]} deltas
 */

/** @type {WeakMap<Object, Map<string, CounterLog>>} */
const logsByTarget = new WeakMap();

/**
 * @param {Object} target
 * @param {string} field
 * @returns {CounterLog}
 */
function getCounterLog(target, field) {
    const raw = toRaw(target)._raw ?? toRaw(target);
    let logs = logsByTarget.get(raw);
    if (!logs) {
        logs = new Map();
        logsByTarget.set(raw, logs);
    }
    const busId = target[`${field}_bus_id`];
    let counterLog = logs.get(field);
    if (counterLog?.busId !== busId) {
        // the bus id moved outside these helpers (a store insert): that value is
        // the only known baseline, the deltas logged before it cannot replay on it
        counterLog = { busId, replayableAfter: busId, deltas: [] };
        logs.set(field, counterLog);
    }
    return counterLog;
}

/**
 * Applies a value the server computed as of `busId`: the deltas already applied
 * from later notifications are replayed on top of it.
 *
 * @param {Object} target
 * @param {string} field
 * @param {number} value
 * @param {number} busId
 * @returns {boolean}
 */
export function applyCounterAbsolute(target, field, value, busId) {
    const busField = `${field}_bus_id`;
    const counterLog = getCounterLog(target, field);
    if (busId < counterLog.replayableAfter) {
        log.logic("counter absolute stale", () => ({
            target: target.localId,
            field,
            busId,
            replayableAfter: counterLog.replayableAfter,
        }));
        return false;
    }
    const later = counterLog.deltas.filter((entry) => entry.busId > busId);
    const replayed = later.reduce((sum, entry) => sum + entry.delta, 0);
    const reconciled = Math.max(value + replayed, 0);
    log.pipeline("counter absolute", () => ({
        target: target.localId,
        field,
        from: target[field],
        value,
        replayed,
        to: reconciled,
        busId,
    }));
    target[field] = reconciled;
    target[busField] = busId;
    Object.assign(counterLog, { busId, replayableAfter: busId, deltas: later });
    return true;
}

/**
 * @param {Object} target
 * @param {string} field
 * @param {number} delta
 * @param {Object} [options]
 * @param {number} [options.floor=0]
 * @param {number} [options.busId]
 * @returns {number}
 */
export function applyCounterDelta(target, field, delta, { floor = 0, busId } = {}) {
    if (busId !== undefined) {
        const counterLog = getCounterLog(target, field);
        if (busId <= target[`${field}_bus_id`]) {
            log.logic("counter delta stale", () => ({
                target: target.localId,
                field,
                delta,
                busId,
                lastSeen: target[`${field}_bus_id`],
            }));
            return 0;
        }
        counterLog.deltas.push({ busId, delta });
        if (counterLog.deltas.length > MAX_LOGGED_DELTAS) {
            counterLog.replayableAfter = counterLog.deltas.shift().busId;
        }
    }
    const value = Math.max(target[field] + delta, floor);
    const applied = value - target[field];
    log.pipeline("counter delta", () => ({
        target: target.localId,
        field,
        delta,
        applied,
        value,
    }));
    if (applied) {
        target[field] = value;
    }
    return applied;
}

/**
 * @param {Object} target
 * @param {string} field
 * @returns {{ restore: () => void, restoreDelta: (delta: number, options?: { floor?: number }) => void }}
 */
export function snapshotCounter(target, field) {
    const busField = `${field}_bus_id`;
    const value = target[field];
    const busId = target[busField];
    return {
        restore() {
            log.logic("counter restore", () => ({
                target: target.localId,
                field,
                value,
                applies: target[busField] === busId,
            }));
            if (target[busField] === busId) {
                target[field] = value;
            }
        },
        /**
         * @param {number} delta
         * @param {Object} [options]
         * @param {number} [options.floor=0]
         */
        restoreDelta(delta, { floor = 0 } = {}) {
            if (target[busField] === busId) {
                applyCounterDelta(target, field, delta, { floor });
            }
        },
    };
}
