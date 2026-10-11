import { describe, expect, test } from "@odoo/hoot";
import { connectablePillPairs, shouldConnectPills } from "@web_gantt/gantt_connectors";

describe.current.tags("headless");

/**
 * Builds the two indexes the renderer derives from its rows: which rows each
 * record has a pill on, and which records each row holds.
 *
 * @param {Record<number, { masterIds: number[], rows: string[] }>} records
 */
function indexes(records) {
    const recordToPillsByRow = {};
    const rowToPillsByRecord = {};
    for (const [id, { masterIds, rows }] of Object.entries(records)) {
        recordToPillsByRow[id] = { masterIds, pills: {} };
        for (const rowId of rows) {
            const pill = { id: `${id}@${rowId}`, record: { id: Number(id) } };
            recordToPillsByRow[id].pills[rowId] = pill;
            rowToPillsByRecord[rowId] ??= {};
            rowToPillsByRecord[rowId][id] = pill;
        }
    }
    return [recordToPillsByRow, rowToPillsByRecord];
}

const pairs = (records) =>
    [...connectablePillPairs(...indexes(records))].map(([s, t]) => `${s.id}->${t.id}`);

test("a master and a slave each on one row connect once, whatever the rows", () => {
    expect(
        pairs({
            1: { masterIds: [], rows: ["A"] },
            2: { masterIds: [1], rows: ["A"] },
        }),
    ).toEqual(["1@A->2@A"]);
    expect(
        pairs({
            1: { masterIds: [], rows: ["A"] },
            2: { masterIds: [1], rows: ["B"] },
        }),
    ).toEqual(["1@A->2@B"]);
});

test("a master whose record is not on the gantt draws nothing", () => {
    expect(pairs({ 2: { masterIds: [1], rows: ["A"] } })).toEqual([]);
});

test("records sharing rows connect within each shared row, not across", () => {
    expect(
        pairs({
            1: { masterIds: [], rows: ["A", "B"] },
            2: { masterIds: [1], rows: ["A", "B"] },
        }),
    ).toEqual(["1@A->2@A", "1@B->2@B"]);
});

test("a slave on a row the master is not on reaches the master's every row", () => {
    expect(
        pairs({
            1: { masterIds: [], rows: ["A", "B"] },
            2: { masterIds: [1], rows: ["C"] },
        }),
    ).toEqual(["1@A->2@C", "1@B->2@C"]);
});

test("a shared row and a private row: the private row still gets its connector", () => {
    const [byRow, byRecord] = indexes({
        1: { masterIds: [], rows: ["A"] },
        2: { masterIds: [1], rows: ["A", "B"] },
    });
    expect(shouldConnectPills(byRow, byRecord, 1, "A", 2, "A")).toBe(true);
    expect(shouldConnectPills(byRow, byRecord, 1, "A", 2, "B")).toBe(true);
    expect(
        pairs({
            1: { masterIds: [], rows: ["A"] },
            2: { masterIds: [1], rows: ["A", "B"] },
        }),
    ).toEqual(["1@A->2@A", "1@A->2@B"]);
});

test("pairs are yielded by slave, then master, then rows -- the connector numbering", () => {
    expect(
        pairs({
            1: { masterIds: [], rows: ["A"] },
            2: { masterIds: [], rows: ["A"] },
            3: { masterIds: [2, 1], rows: ["B", "A"] },
        }),
    ).toEqual(["2@A->3@B", "2@A->3@A", "1@A->3@B", "1@A->3@A"]);
});
