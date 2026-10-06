// @ts-check
/** @odoo-module native */

import { toRaw } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { isX2Many } from "@web/core/field_types";
import { x2ManyCommands } from "@web/core/network/commands";

import { listId } from "./static_list_utils.js";

/** @import { RecordContract } from "./record_contract.js" */

/** @import { StaticListContract } from "./static_list_contract.js" */

const log = makeLogger("web.model.x2many");

/**
 * @param {RecordContract} record
 * @returns {Generator<[string, StaticListContract]>}
 */
export function* allX2manyLists(record) {
    for (const fieldName of Object.keys(record.activeFields)) {
        if (!isX2Many(record.fields[fieldName])) {
            continue;
        }
        const list = record.data[fieldName];
        if (list) {
            yield [fieldName, list];
        }
    }
}

/**
 * @param {RecordContract} record
 * @returns {Generator<[string, StaticListContract]>}
 */
export function* x2manyLists(record) {
    for (const [fieldName, list] of allX2manyLists(record)) {
        if (!record.fields[fieldName].relatedPropertyField) {
            yield [fieldName, list];
        }
    }
}

/**
 * @param {RecordContract} record
 * @returns {Generator<[string, StaticListContract]>}
 */
export function* walkX2manySubtree(record) {
    const seen = new Set();
    /**
     * @param {RecordContract} current
     * @returns {Generator<[string, StaticListContract]>}
     */
    function* visit(current) {
        for (const [fieldName, list] of allX2manyLists(current)) {
            if (seen.has(list)) {
                continue;
            }
            seen.add(list);
            yield [fieldName, list];
            for (const subRecord of list.cachedRecords) {
                if (!seen.has(subRecord)) {
                    seen.add(subRecord);
                    yield* visit(subRecord);
                }
            }
        }
    }
    yield* visit(record);
}

/**
 * @param {RecordContract} record
 * @returns {Promise<unknown>[]}
 */
export function collectPendingCommands(record) {
    /** @type {Promise<unknown>[]} */
    const proms = [];
    for (const [, list] of walkX2manySubtree(record)) {
        if (list.pendingCommands) {
            proms.push(list.pendingCommands);
        }
    }
    return proms;
}

/** @param {RecordContract} record */
export function healSubtreeReplayFailures(record) {
    for (const [, list] of walkX2manySubtree(record)) {
        list.healFailedReplay();
    }
}

/**
 * @param {RecordContract} record
 * @param {Set<unknown>} [seen]
 * @returns {Record<string, any>}
 */
export function getCommitSpec(record, seen = new Set()) {
    /** @type {Record<string, any>} */
    const spec = {};
    if (seen.has(record)) {
        return spec;
    }
    seen.add(record);
    for (const [fieldName, list] of x2manyLists(record)) {
        const nested = {};
        for (const child of list.cachedRecords) {
            Object.assign(nested, getCommitSpec(child, seen));
        }
        const hasNested = Object.keys(nested).length > 0;
        if (!list.hasStagedCommands && !hasNested) {
            continue;
        }
        spec[fieldName] = hasNested ? { fields: nested } : {};
    }
    return spec;
}

/**
 * @param {RecordContract} record
 * @returns {Map<object, Record<string, unknown>>}
 */
export function snapshotRowChanges(record) {
    /** @type {Map<object, Record<string, unknown>>} */
    const snapshot = new Map();
    for (const [, list] of walkX2manySubtree(record)) {
        for (const row of list.cachedRecords) {
            const raw = toRaw(row);
            if (Object.keys(raw.changes).length) {
                snapshot.set(raw, { ...raw.changes });
            }
        }
    }
    return snapshot;
}

/**
 * @param {RecordContract} record
 * @param {(row: any) => boolean} predicate
 * @returns {boolean}
 */
export function someSubtreeRow(record, predicate) {
    for (const [, list] of walkX2manySubtree(record)) {
        if (list.cachedRecords.some(predicate)) {
            return true;
        }
    }
    return false;
}

/**
 * @typedef {{ isLate?: (row: any) => boolean }} CommitOptions
 */

/**
 * @param {RecordContract} record
 * @param {Record<string, any>} [values]
 * @param {CommitOptions} [options]
 * @param {Set<unknown>} [seen]
 * @returns {Set<string>} the x2many fields of `record` still holding late rows
 */
export function commitSubtree(record, values, options = {}, seen = new Set()) {
    /** @type {Set<string>} */
    const lateFields = new Set();
    if (seen.has(record)) {
        return lateFields;
    }
    seen.add(record);
    for (const [fieldName, list] of x2manyLists(record)) {
        const serverValue = values?.[fieldName];
        /** @type {RecordContract[]} */
        const lateRows = [];
        /**
         * @param {RecordContract} child
         * @param {Record<string, any> | undefined} childValues
         */
        const visit = (child, childValues) => {
            if (commitRow(child, childValues, options, seen)) {
                lateRows.push(child);
            }
        };
        if (serverValue === undefined) {
            for (const child of list.cachedRecords) {
                visit(child, undefined);
            }
            list.clearCommands();
        } else {
            list.commitSave(serverValue);
            for (const row of serverValue) {
                const isObject = Boolean(row) && typeof row === "object";
                const child = list.getCachedRecord(isObject ? row.id : row);
                if (child) {
                    visit(child, isObject ? row : undefined);
                }
            }
        }
        if (lateRows.length) {
            list.commitCommands(
                lateRows.map((row) => [
                    x2ManyCommands.UPDATE,
                    listId(/** @type {any} */ (row)),
                ]),
            );
            lateFields.add(fieldName);
        }
    }
    return lateFields;
}

/**
 * @param {RecordContract} child
 * @param {Record<string, any> | undefined} values
 * @param {CommitOptions} options
 * @param {Set<unknown>} seen
 * @returns {boolean} whether the row, or a row below it, changed after it was sent
 */
function commitRow(child, values, options, seen) {
    if (seen.has(child)) {
        return false;
    }
    const lateBelow = commitSubtree(child, values, options, seen).size > 0;
    if (!child.hasPendingChanges) {
        return lateBelow;
    }
    const late = lateBelow || Boolean(options.isLate?.(child));
    log.logic("commitRow", () => ({
        id: listId(/** @type {any} */ (child)),
        late,
        lateBelow,
    }));
    if (!late) {
        child.commitChanges();
    }
    return late;
}
