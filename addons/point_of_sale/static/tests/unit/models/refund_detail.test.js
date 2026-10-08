import { describe, expect, test } from "@odoo/hoot";
import { PosOrderLineRefund } from "@point_of_sale/app/models/pos_order_line_refund";

import { definePosModels } from "../data/generate_model_definitions.js";
import { getFilledOrder, setupPosEnv } from "../utils.js";

definePosModels();

/** The ticket screen's own shape: the detail is stored on the order that owns
 * the line being refunded, keyed by that line's uuid. */
async function anOrderBeingRefunded(store) {
    const original = await getFilledOrder(store);
    const originalLine = original.lines[0];
    const detail = new PosOrderLineRefund(
        { line_uuid: originalLine.uuid, qty: 1 },
        store.models,
    );
    original.uiState.lineToRefund[originalLine.uuid] = detail;

    const refundOrder = store.addNewOrder();
    const refundLine = store.models["pos.order.line"].create({
        order_id: refundOrder,
        product_id: originalLine.product_id,
        qty: -1,
        price_unit: originalLine.price_unit,
        refunded_orderline_id: originalLine,
    });
    return { original, originalLine, refundOrder, refundLine };
}

describe("a refund detail lives on the refunded order", () => {
    test("removing the refund line clears it", async () => {
        const store = await setupPosEnv();
        const { original, originalLine, refundOrder, refundLine } =
            await anOrderBeingRefunded(store);
        expect(originalLine.uuid in original.uiState.lineToRefund).toBe(true);

        refundOrder.removeOrderline(refundLine);

        expect(originalLine.uuid in original.uiState.lineToRefund).toBe(false);
    });

    test("setQuantity finds the detail without merging every order's map", async () => {
        const store = await setupPosEnv();
        const { refundLine } = await anOrderBeingRefunded(store);
        const refusal = refundLine.setQuantity(2);
        expect(refusal).not.toBe(true);
        expect(refusal.title).toBeOfType("string");
        expect(refundLine.setQuantity(-1)).toBe(true);
    });
});

describe("the till counts a draft refund made elsewhere", () => {
    test("it refuses what the server's guard, which counts only settled refunds, would accept", async () => {
        const store = await setupPosEnv();
        const { originalLine, refundLine } = await anOrderBeingRefunded(store);
        // the server's refunded_qty includes a 2-unit draft refund on another till;
        // the cash of a till refund is handed back at once, so the till stays stricter
        originalLine.refunded_qty = 2;

        expect(originalLine.qty).toBe(3);
        expect(originalLine.refundedQty).toBe(3);
        expect(refundLine.setQuantity(-2)).not.toBe(true);
        expect(refundLine.setQuantity(-1)).toBe(true);
    });
});

/** A synced refund line of `originalLine`: the server's refunded_qty counts it. */
async function aSyncedRefund(store, originalLine, id, qty) {
    const refundOrder = store.addNewOrder();
    return store.models["pos.order.line"].create({
        id,
        order_id: refundOrder,
        product_id: originalLine.product_id,
        qty,
        price_unit: originalLine.price_unit,
        refunded_orderline_id: originalLine,
    });
}

describe("a synced refund line edited on this till", () => {
    test("counts once: its old quantity leaves the server's count", async () => {
        const store = await setupPosEnv();
        const original = await getFilledOrder(store);
        const originalLine = original.lines[0];
        originalLine.qty = 2;
        original.uiState.lineToRefund[originalLine.uuid] = new PosOrderLineRefund(
            { line_uuid: originalLine.uuid, qty: 1 },
            store.models,
        );
        const refund = await aSyncedRefund(store, originalLine, 9101, -1);
        originalLine.refunded_qty = 1;

        expect(refund.setQuantity(0)).toBe(true);
        expect(originalLine.refundedQty).toBe(0);
        expect(refund.setQuantity(-2)).toBe(true);
        expect(originalLine.refundedQty).toBe(2);
        expect(refund.setQuantity(-3)).not.toBe(true);
    });

    test("still counts another line's edit and what only the server knows", async () => {
        const store = await setupPosEnv();
        const original = await getFilledOrder(store);
        const originalLine = original.lines[0];
        originalLine.qty = 5;
        original.uiState.lineToRefund[originalLine.uuid] = new PosOrderLineRefund(
            { line_uuid: originalLine.uuid, qty: 1 },
            store.models,
        );
        const other = await aSyncedRefund(store, originalLine, 9102, -1);
        const refund = await aSyncedRefund(store, originalLine, 9103, -1);
        // 1 more was refunded in a session this till has not loaded
        originalLine.refunded_qty = 3;
        expect(originalLine.refundedQty).toBe(3);

        expect(refund.setQuantity(-3)).toBe(true);
        expect(refund.setQuantity(-4)).not.toBe(true);

        other.update({ qty: -2 });
        expect(originalLine.refundedQty).toBe(6);
        expect(refund.setQuantity(-3)).not.toBe(true);
        expect(refund.setQuantity(-2)).toBe(true);
    });

    test("is counted from the synced quantity it kept through a reload", async () => {
        const store = await setupPosEnv();
        const original = await getFilledOrder(store);
        const originalLine = original.lines[0];
        originalLine.qty = 2;
        const refund = await aSyncedRefund(store, originalLine, 9104, -1);
        originalLine.refunded_qty = 1;
        refund.update({ qty: -2 });
        const row = JSON.parse(JSON.stringify(refund.serializeForIndexedDB()));
        expect(row.__dirty).toBe(true);

        // a reload restores the row; under new keys, as the deleted ones stay pending
        const refundOrder = refund.order_id;
        refund.delete({ silent: true });
        store.models["pos.order.line"].create({
            id: 9105,
            __dirty: row.__dirty,
            JSONuiState: row.JSONuiState,
            order_id: refundOrder,
            product_id: originalLine.product_id,
            qty: row.qty,
            price_unit: row.price_unit,
            refunded_orderline_id: originalLine,
        });
        expect(originalLine.refund_orderline_ids.map((line) => line.id)).toEqual([
            9105,
        ]);
        expect(originalLine.refundedQty).toBe(2);
    });
});
