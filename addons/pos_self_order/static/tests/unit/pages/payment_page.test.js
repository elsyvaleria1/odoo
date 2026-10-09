import { expect, test } from "@odoo/hoot";
import { queryAll } from "@odoo/hoot-dom";
import { PaymentPage } from "@pos_self_order/app/pages/payment_page/payment_page";
import { mountWithCleanup, onRpc } from "@web/../tests/web_test_helpers";

import { definePosSelfModels } from "../data/generate_model_definitions.js";
import { getFilledSelfOrder, setupSelfPosEnv } from "../utils.js";

definePosSelfModels();

const mountPaymentPage = async () => {
    const store = await setupSelfPosEnv();
    const order = await getFilledSelfOrder(store);
    const requested = [];
    onRpc("/kiosk/payment/1/kiosk", () => {
        requested.push(order.uuid);
        return {};
    });
    const method = store.models["pos.payment.method"].getFirst();
    return { store, order, method, requested };
};

test("a kiosk order whose payment is being verified takes no new payment", async () => {
    const { order, method, requested } = await mountPaymentPage();
    order.kiosk_payment_to_verify_method_id = method;
    const page = await mountWithCleanup(PaymentPage, {});

    page.selectMethod(method.id);
    await page.startPayment();

    expect(requested).toEqual([]);
    expect(queryAll(".o_self_payment_to_verify")).toHaveLength(1);
    expect(queryAll("button:contains(Retry)")).toHaveLength(0);
});

test("once staff settle the verification, the kiosk can pay again", async () => {
    const { order, method, requested } = await mountPaymentPage();
    order.kiosk_payment_to_verify_method_id = method;
    const page = await mountWithCleanup(PaymentPage, {});
    order.kiosk_payment_to_verify_method_id = false;

    page.selectMethod(method.id);
    await page.startPayment();

    expect(requested).not.toEqual([]);
});
