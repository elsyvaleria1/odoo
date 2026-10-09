import { beforeEach, expect, test } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { onRpc } from "@web/../tests/web_test_helpers";

definePosModels();

const PINE_LABS_METHOD_ID = 13;

beforeEach(() => {
    PosPaymentMethod._records = [
        ...PosPaymentMethod._records,
        {
            id: PINE_LABS_METHOD_ID,
            name: "Pine Labs",
            is_cash_count: false,
            use_payment_terminal: "pine_labs",
            split_transactions: false,
            type: "bank",
            image: false,
            sequence: 3,
            payment_method_type: "terminal",
            default_qr: false,
        },
    ];
    PosConfig._records = PosConfig._records.map((config) => ({
        ...config,
        payment_method_ids: [...config.payment_method_ids, PINE_LABS_METHOD_ID],
    }));
});

test("payment and cancel requests carry the amount in paisa, rounded", async () => {
    const amounts = {};
    for (const action of [
        "pine_labs_make_payment_request",
        "pine_labs_cancel_payment_request",
    ]) {
        onRpc("pos.payment.method", action, ({ args }) => {
            amounts[action] = args[1].amount;
            return { error: "stop here" };
        });
    }
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(PINE_LABS_METHOD_ID);
    const { data: line } = order.addPaymentline(method);
    line.setAmount(19.99);

    await method.payment_terminal._processPineLabs();
    line.setPaymentStatus("waitingCard");
    await method.payment_terminal._pineLabsCancel();

    expect(amounts).toEqual({
        pine_labs_make_payment_request: 1999,
        pine_labs_cancel_payment_request: 1999,
    });
});
