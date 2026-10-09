import { beforeEach, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { advanceTime } from "@odoo/hoot-mock";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { onRpc } from "@web/../tests/web_test_helpers";

definePosModels();

const MOLLIE_METHOD_ID = 15;

beforeEach(() => {
    PosPaymentMethod._records = [
        ...PosPaymentMethod._records,
        {
            id: MOLLIE_METHOD_ID,
            name: "Mollie",
            is_cash_count: false,
            use_payment_terminal: "mollie",
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
        payment_method_ids: [...config.payment_method_ids, MOLLIE_METHOD_ID],
    }));
});

test("polling confirms the payment when the bus notification is lost", async () => {
    const polled = [];
    onRpc("pos.payment.method", "mollie_create_payment", () => ({
        id: "tr_1",
        status: "open",
        _links: {},
    }));
    onRpc("pos.payment.method", "mollie_get_payment_status", ({ args }) => {
        polled.push(args[1]);
        return { payment_id: args[1], status: "paid", card_brand: "Visa" };
    });
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(MOLLIE_METHOD_ID);
    const { data: line } = order.addPaymentline(method);
    line.pay();
    await waitUntil(() => line.transaction_id === "tr_1");

    await advanceTime(5000);
    await waitUntil(() => line.getPaymentStatus() === "done", { timeout: 1000 });

    expect(polled).toEqual(["tr_1"]);
    expect(line.card_brand).toBe("Visa");
});
