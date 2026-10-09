import { beforeEach, expect, test } from "@odoo/hoot";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { definePosRestaurantModels } from "@pos_restaurant/../tests/unit/data/generate_model_definitions";
import { onRpc } from "@web/../tests/web_test_helpers";

definePosRestaurantModels();

const ADYEN_METHOD_ID = 14;

beforeEach(() => {
    PosPaymentMethod._records = [
        ...PosPaymentMethod._records,
        {
            id: ADYEN_METHOD_ID,
            name: "Adyen",
            is_cash_count: false,
            use_payment_terminal: "adyen",
            split_transactions: false,
            type: "bank",
            image: false,
            sequence: 3,
            payment_method_type: "terminal",
            default_qr: false,
            adyen_terminal_identifier: "P400Plus-123",
            adyen_merchant_account: "Merchant",
        },
    ];
    PosConfig._records = PosConfig._records.map((config) => ({
        ...config,
        payment_method_ids: [...config.payment_method_ids, ADYEN_METHOD_ID],
    }));
});

test("a tip adjustment asks for the amount in minor units, rounded", async () => {
    const adjusted = [];
    onRpc("pos.payment.method", "proxy_adyen_request", ({ args }) => {
        adjusted.push(args[1].modificationAmount.value);
        return true;
    });
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(ADYEN_METHOD_ID);
    const { data: line } = order.addPaymentline(method);
    line.setAmount(19.99);
    line.transaction_id = "PSP1";

    await method.payment_terminal.sendPaymentAdjust(line.uuid);

    expect(adjusted).toEqual([1999]);
});
