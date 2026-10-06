/** @odoo-module native */

/**
 * @typedef {import("./gantt_renderer_core").Pill} Pill
 * @typedef {import("./gantt_renderer_core").RowId} RowId
 * @typedef {Record<number, { masterIds: number[], pills: Record<RowId, Pill> }>} RecordToPillsByRow
 * @typedef {Record<RowId, Record<number, Pill>>} RowToPillsByRecord
 */

/**
 * @param {RecordToPillsByRow} recordToPillsByRow
 * @param {RowToPillsByRecord} rowToPillsByRecord
 * @param {number} masterId
 * @param {RowId} masterRowId
 * @param {number} slaveId
 * @param {RowId} slaveRowId
 * @returns {boolean}
 */
export function shouldConnectPills(
    recordToPillsByRow,
    rowToPillsByRecord,
    masterId,
    masterRowId,
    slaveId,
    slaveRowId,
) {
    return (
        masterRowId === slaveRowId ||
        !(
            slaveId in rowToPillsByRecord[masterRowId] ||
            masterId in rowToPillsByRecord[slaveRowId]
        ) ||
        Object.keys(recordToPillsByRow[slaveId].pills).every(
            (rowId) => rowId !== masterRowId && masterId in rowToPillsByRecord[rowId],
        ) ||
        Object.keys(recordToPillsByRow[masterId].pills).every(
            (rowId) => rowId !== slaveRowId && slaveId in rowToPillsByRecord[rowId],
        )
    );
}

/**
 * @param {RecordToPillsByRow} recordToPillsByRow
 * @param {RowToPillsByRecord} rowToPillsByRecord
 * @returns {Generator<[Pill, Pill]>}
 */
export function* connectablePillPairs(recordToPillsByRow, rowToPillsByRecord) {
    for (const slaveId in recordToPillsByRow) {
        const { masterIds, pills: slavePills } = recordToPillsByRow[slaveId];
        for (const masterId of masterIds) {
            if (!(masterId in recordToPillsByRow)) {
                continue;
            }
            const { pills: masterPills } = recordToPillsByRow[masterId];
            for (const [slaveRowId, targetPill] of Object.entries(slavePills)) {
                for (const [masterRowId, sourcePill] of Object.entries(masterPills)) {
                    if (
                        shouldConnectPills(
                            recordToPillsByRow,
                            rowToPillsByRecord,
                            masterId,
                            masterRowId,
                            Number(slaveId),
                            slaveRowId,
                        )
                    ) {
                        yield [sourcePill, targetPill];
                    }
                }
            }
        }
    }
}
