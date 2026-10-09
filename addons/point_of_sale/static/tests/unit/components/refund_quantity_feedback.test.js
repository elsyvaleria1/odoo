import { describe, expect, test } from "@odoo/hoot";
import { PosOrderLineRefund } from "@point_of_sale/app/models/pos_order_line_refund";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { MockServer, mountWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosModels } from "../data/generate_model_definitions.js";
import { getFilledOrder, setupPosEnv } from "../utils.js";

definePosModels();

async function aSelectedRefundLine(store) {
    const original = await getFilledOrder(store);
    const originalLine = original.lines[0];
    original.uiState.lineToRefund[originalLine.uuid] = new PosOrderLineRefund(
        { line_uuid: originalLine.uuid, qty: 1 },
        store.models,
    );

    const refundOrder = store.addNewOrder();
    const refundLine = store.models["pos.order.line"].create({
        order_id: refundOrder,
        product_id: originalLine.product_id,
        qty: -1,
        price_unit: originalLine.price_unit,
        refunded_orderline_id: originalLine,
    });
    refundOrder.selectOrderline(refundLine);
    return refundLine;
}

describe("a refused refund quantity reaches the cashier", () => {
    test("the numpad path reports the refusal", async () => {
        const store = await setupPosEnv();
        const refundLine = await aSelectedRefundLine(store);
        const component = await mountWithCleanup(OrderSummary, {});
        const dialogs = [];
        component.dialog = { add: (_, props) => dialogs.push(props) };

        store.numpadMode = "quantity";
        component._setValue(2);

        expect(refundLine.getQuantity()).toBe(-1);
        expect(dialogs).toHaveLength(1);
        expect(dialogs[0].title).toBe("Positive quantity not allowed");
    });

    test("the popup path reports it too", async () => {
        const store = await setupPosEnv();
        const refundLine = await aSelectedRefundLine(store);
        const component = await mountWithCleanup(OrderSummary, {});
        const dialogs = [];
        component.dialog = { add: (_, props) => dialogs.push(props) };

        await component.updateQuantityNumber(2);

        expect(refundLine.getQuantity()).toBe(-1);
        expect(dialogs).toHaveLength(1);
        expect(dialogs[0].title).toBe("Positive quantity not allowed");
    });
});

describe("a refund keyed on a ticket screen left open", () => {
    test("is refused once the server says another till refunded the line meanwhile", async () => {
        const store = await setupPosEnv();
        const sale = await getFilledOrder(store);
        await store.syncAllOrders({ orders: [sale] });
        sale.state = "paid";
        const soldLine = sale.lines[0];
        sale.uiState.lineToRefund[soldLine.uuid] = new PosOrderLineRefund(
            { line_uuid: soldLine.uuid, qty: 2 },
            store.models,
        );
        const screen = await mountWithCleanup(TicketScreen, {
            props: { reuseSavedUIState: false },
        });
        screen.setSelectedOrder(sale);
        const dialogs = [];
        store.dialog = { add: (_, props) => dialogs.push(props) };
        MockServer.env["pos.order.line"].write([soldLine.id], { refunded_qty: 2 });

        await screen.onDoRefund();

        expect(soldLine.qty).toBe(3);
        expect(soldLine.refundedQty).toBe(2);
        expect(dialogs.map((props) => props.title)).toEqual(["Maximum Exceeded"]);
        expect(
            store.models["pos.order.line"].filter((line) => line.refunded_orderline_id),
        ).toHaveLength(0);
    });
});
