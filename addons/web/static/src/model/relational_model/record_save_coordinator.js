// @ts-check
/** @odoo-module native */

import { toRaw } from "@odoo/owl";

/**
 * @param {Record<string, unknown>} sent
 * @param {Record<string, unknown>} changes
 * @returns {Record<string, unknown>}
 */
function diffChanges(sent, changes) {
    /** @type {Record<string, unknown>} */
    const late = {};
    for (const [fieldName, value] of Object.entries(changes)) {
        if (!(fieldName in sent) || sent[fieldName] !== value) {
            late[fieldName] = value;
        }
    }
    return late;
}

/** @typedef {"idle" | "saving"} RecordSaveStatus */

export class RecordSaveCoordinator {
    constructor() {
        /** @type {RecordSaveStatus} */
        this.status = "idle";
        this._beaconFired = false;
        /** @type {Record<string, unknown>} */
        this._sentChanges = {};
        /** @type {Map<object, Record<string, unknown>>} */
        this._sentRows = new Map();
        this._holdsLock = false;
    }

    /** @returns {boolean} whether the save in flight is a job of the model mutex */
    get holdsLock() {
        return this._holdsLock;
    }

    /** @returns {boolean} */
    get isInFlight() {
        return this.status === "saving";
    }

    /**
     * @param {Record<string, unknown>} [sentChanges]
     * @param {Map<object, Record<string, unknown>>} [sentRows]
     * @param {{ holdsLock?: boolean }} [options]
     * @returns {void}
     */
    enter(sentChanges = {}, sentRows = new Map(), { holdsLock = false } = {}) {
        this.status = "saving";
        this._sentChanges = { ...sentChanges };
        this._sentRows = sentRows;
        this._holdsLock = holdsLock;
    }

    /** @returns {void} */
    exit() {
        this.status = "idle";
        this._sentChanges = {};
        this._sentRows = new Map();
        this._holdsLock = false;
    }

    /**
     * @param {Record<string, unknown>} changes
     * @returns {Record<string, unknown>}
     */
    lateChanges(changes) {
        return diffChanges(this._sentChanges, changes);
    }

    /**
     * @param {{ changes: Record<string, unknown> }} row
     * @returns {boolean}
     */
    isRowLate(row) {
        const raw = toRaw(row);
        const sent = this._sentRows.get(raw) ?? {};
        return Object.keys(diffChanges(sent, raw.changes)).length > 0;
    }

    /** @returns {boolean} */
    get beaconFired() {
        return this._beaconFired;
    }

    /** @returns {void} */
    noteBeaconFired() {
        this._beaconFired = true;
    }

    /** @returns {void} */
    clearBeacon() {
        this._beaconFired = false;
    }

    /** @returns {boolean} */
    consumeBeaconFired() {
        const fired = this._beaconFired;
        this._beaconFired = false;
        return fired;
    }
}
