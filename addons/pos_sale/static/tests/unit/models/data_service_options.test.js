import { describe, expect, test } from "@odoo/hoot";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosSaleModels } from "../data/generate_model_definitions.js";

definePosSaleModels();

async function aLineSettlingASaleOrder() {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const saleOrder = store.models["sale.order"].get(1);
    const saleOrderLine = store.models["sale.order.line"].get(1);
    order.lines[0].update({
        sale_order_origin_id: saleOrder,
        sale_order_line_id: saleOrderLine,
    });
    const put = [];
    const removed = [];
    patchWithCleanup(store.data.indexedDB, {
        create: async (model, rows) => {
            put.push(...rows.map((row) => `${model}:${row.id}`));
            return rows.map(() => ({ status: "fulfilled" }));
        },
        delete: async (model, keys) => {
            removed.push(...keys.map((key) => `${model}:${key}`));
        },
    });
    const ofSale = (rows) => rows.filter((row) => row.startsWith("sale.")).sort();
    return {
        store,
        line: order.lines[0],
        put: () => ofSale(put),
        removed: () => ofSale(removed),
    };
}

describe("a sale order is kept in IndexedDB while a POS line points at it", () => {
    test("an edit of the line writes its sale order and line", async () => {
        const { store, line, put, removed } = await aLineSettlingASaleOrder();
        store.data.dirtyLocalRecords.clear();
        store.data.markLocalRecordsDirty("pos.order.line", [line.id]);

        await store.data._synchronizeLocalDataInIndexedDB({ onlyDirty: true });

        expect(put()).toEqual(["sale.order.line:1", "sale.order:1"]);
        expect(removed()).toEqual([]);
    });

    test("a full flush keeps the linked ones and drops the others", async () => {
        const { store, put, removed } = await aLineSettlingASaleOrder();

        await store.data._synchronizeLocalDataInIndexedDB();

        expect(put()).toEqual(["sale.order.line:1", "sale.order:1"]);
        expect(removed()).toEqual(["sale.order.line:2"]);
    });
});
