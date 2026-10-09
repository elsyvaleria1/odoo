import { expect, test } from "@odoo/hoot";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { Command, MockServer, patchWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosModels } from "../data/generate_model_definitions.js";
import { getFilledOrder, setupPosEnv } from "../utils.js";

definePosModels();

test("validateOrder", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const fastPaymentMethod = order.config.fast_payment_method_ids[0];
    const validation = new OrderPaymentValidation({
        pos: store,
        orderUuid: store.getOrder().uuid,
        fastPaymentMethod: fastPaymentMethod,
    });
    await validation.validateOrder(false);
    expect(order.payment_ids[0].payment_method_id).toEqual(fastPaymentMethod);
    expect(order.state).toBe("paid");
    expect(order.amount_paid).toBe(17.85);
});
test("validation is refused while a terminal payment is in flight", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const cashMethod = store.models["pos.payment.method"].find(
        (pm) => pm.is_cash_count,
    );
    const terminalLine = order.addPaymentline(cashMethod).data;
    const cashLine = order.addPaymentline(cashMethod).data;
    terminalLine.setAmount(0);
    cashLine.setAmount(order.totalDue);
    terminalLine.setPaymentStatus("waiting");

    const validation = new OrderPaymentValidation({
        pos: store,
        orderUuid: order.uuid,
    });
    expect(await validation.isOrderValid(false)).toBe(false);
    terminalLine.setPaymentStatus("done");
    expect(await validation.isOrderValid(false)).toBe(true);
});

test("isOrderValid", async () => {
    const store = await setupPosEnv();
    const order = store.addNewOrder();
    order.setToInvoice(true);
    const validation = new OrderPaymentValidation({
        pos: store,
        orderUuid: store.getOrder().uuid,
    });
    const isOrderValid = await validation.isOrderValid(false);
    expect(order.lines).toHaveLength(0);
    expect(isOrderValid).toBe(false);
});

test("a refund is not validated past what the server says is left to refund", async () => {
    const store = await setupPosEnv();
    const sale = await getFilledOrder(store);
    await store.syncAllOrders({ orders: [sale] });
    const soldLine = sale.lines[0];
    const refund = store.addNewOrder();
    store.models["pos.order.line"].create({
        order_id: refund,
        product_id: soldLine.product_id,
        qty: -2,
        price_unit: soldLine.price_unit,
        refunded_orderline_id: soldLine,
    });
    const cashMethod = store.models["pos.payment.method"].find(
        (pm) => pm.is_cash_count,
    );
    refund.addPaymentline(cashMethod).data.setAmount(refund.totalDue);
    const dialogs = [];
    store.dialog = { add: (_, props) => dialogs.push(props) };
    const validation = new OrderPaymentValidation({
        pos: store,
        orderUuid: refund.uuid,
    });
    expect(await validation.isOrderValid(false)).toBe(true);

    MockServer.env["pos.order.line"].write([soldLine.id], { refunded_qty: 2 });

    expect(await validation.isOrderValid(false)).toBe(false);
    expect(soldLine.refundedQty).toBe(4);
    expect(dialogs.map((props) => props.title)).toEqual(["Maximum Exceeded"]);
});

test("a refund refused for a draft refund elsewhere names that draft", async () => {
    const store = await setupPosEnv();
    const sale = await getFilledOrder(store);
    await store.syncAllOrders({ orders: [sale] });
    const soldLine = sale.lines[0];
    const refund = store.addNewOrder();
    store.models["pos.order.line"].create({
        order_id: refund,
        product_id: soldLine.product_id,
        qty: -2,
        price_unit: soldLine.price_unit,
        refunded_orderline_id: soldLine,
    });
    const cashMethod = store.models["pos.payment.method"].find(
        (pm) => pm.is_cash_count,
    );
    refund.addPaymentline(cashMethod).data.setAmount(refund.totalDue);
    const dialogs = [];
    store.dialog = { add: (_, props) => dialogs.push(props) };
    const elsewhere = MockServer.env["pos.order"].create({
        state: "draft",
        config_id: 1,
        lines: [
            Command.create({
                product_id: soldLine.product_id.id,
                qty: -2,
                price_unit: soldLine.price_unit,
                refunded_orderline_id: soldLine.id,
            }),
        ],
    });
    MockServer.env["pos.order"].write([elsewhere], { pos_reference: "Shop/0042" });
    MockServer.env["pos.order.line"].write([soldLine.id], { refunded_qty: 2 });
    const validation = new OrderPaymentValidation({
        pos: store,
        orderUuid: refund.uuid,
    });

    expect(await validation.isOrderValid(false)).toBe(false);
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0].body).toInclude("2 is held by draft refund Shop/0042 on");
});

test("an offline refund is validated on what the till knows, for the server to flag", async () => {
    const store = await setupPosEnv();
    const sale = await getFilledOrder(store);
    await store.syncAllOrders({ orders: [sale] });
    const soldLine = sale.lines[0];
    const refund = store.addNewOrder();
    store.models["pos.order.line"].create({
        order_id: refund,
        product_id: soldLine.product_id,
        qty: -2,
        price_unit: soldLine.price_unit,
        refunded_orderline_id: soldLine,
    });
    const cashMethod = store.models["pos.payment.method"].find(
        (pm) => pm.is_cash_count,
    );
    refund.addPaymentline(cashMethod).data.setAmount(refund.totalDue);
    MockServer.env["pos.order.line"].write([soldLine.id], { refunded_qty: 2 });
    store.data.network.offline = true;
    const validation = new OrderPaymentValidation({
        pos: store,
        orderUuid: refund.uuid,
    });

    expect(await validation.isOrderValid(false)).toBe(true);
    expect(soldLine.refunded_qty).toBe(0);
});

test("an order the server flags as refunding more than was sold is announced once", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const call = store.data.call.bind(store.data);
    store.data.call = async (model, method, args, kwargs) => {
        const result = await call(model, method, args, kwargs);
        if (method === "sync_from_ui") {
            for (const row of result["pos.order"]) {
                row.is_over_refund = row.uuid === order.uuid;
            }
        }
        return result;
    };
    patchWithCleanup(store.notification, {
        add: (message, options) => expect.step(options.type),
    });

    await store.syncAllOrders({ orders: [order], force: true });
    await store.syncAllOrders({ orders: [order], force: true });

    expect(order.is_over_refund).toBe(true);
    expect.verifySteps(["warning"]);
});
