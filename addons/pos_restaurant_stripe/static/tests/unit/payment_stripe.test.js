import { after, beforeEach, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { definePosRestaurantModels } from "@pos_restaurant/../tests/unit/data/generate_model_definitions";
import { PaymentStripe } from "@pos_stripe/app/payment_stripe";
import { onRpc } from "@web/../tests/web_test_helpers";

definePosRestaurantModels();

const STRIPE_METHOD_ID = 10;

beforeEach(() => {
    PosPaymentMethod._records = [
        ...PosPaymentMethod._records,
        {
            id: STRIPE_METHOD_ID,
            name: "Stripe",
            is_cash_count: false,
            use_payment_terminal: "stripe",
            split_transactions: false,
            type: "bank",
            image: false,
            sequence: 3,
            payment_method_type: "terminal",
            default_qr: false,
            stripe_serial_number: "S1",
        },
    ];
    PosConfig._records = PosConfig._records.map((config) => ({
        ...config,
        payment_method_ids: [...config.payment_method_ids, STRIPE_METHOD_ID],
    }));
    window.StripeTerminal = {
        create: () => ({
            discoverReaders: async () => ({ discoveredReaders: [] }),
            getConnectionStatus: () => "connected",
        }),
    };
    after(() => delete window.StripeTerminal);
});

test("a payment resumed at startup, with no order selected yet, keeps its capture for the tip", async () => {
    const captured = [];
    onRpc("pos.payment.method", "stripe_capture_payment", ({ args }) => {
        captured.push(args[0]);
        return { id: args[0], charges: false };
    });
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(STRIPE_METHOD_ID);
    const { data: line } = order.addPaymentline(method);
    line.transaction_id = "pi_RELOADED";
    line.setPaymentStatus("waitingCapture");
    store.selectedOrderUuid = null;

    method.payment_terminal = new PaymentStripe(store, method);
    await waitUntil(() => line.getPaymentStatus() !== "waitingCapture");

    expect(store.config.set_tip_after_payment).toBe(true);
    expect(captured).toEqual([]);
    expect(line.getPaymentStatus()).toBe("done");
});
