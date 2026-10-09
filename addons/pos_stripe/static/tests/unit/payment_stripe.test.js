import { after, beforeEach, describe, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { PaymentStripe } from "@pos_stripe/app/payment_stripe";
import { onRpc } from "@web/../tests/web_test_helpers";

definePosModels();

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
            discoverReaders: async () => ({
                discoveredReaders: [{ serial_number: "S1" }],
            }),
            getConnectionStatus: () => "connected",
            collectPaymentMethod: async () => ({ paymentIntent: { id: "pi_AUTH" } }),
            processPayment: async (paymentIntent) => ({
                paymentIntent: { id: paymentIntent.id },
            }),
        }),
    };
    after(() => delete window.StripeTerminal);
    onRpc("/css", () => "");
    onRpc("/fonts/*", () => "");
    onRpc("/web/static/*", () => "");
    onRpc("pos.payment.method", "stripe_connection_token", () => ({ secret: "tok" }));
    onRpc("pos.payment.method", "stripe_payment_intent", () => ({
        client_secret: "pi_AUTH_secret",
    }));
});

const setupStripeLine = async () => {
    const store = await setupPosEnv();
    store.connectedReader = "S1";
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(STRIPE_METHOD_ID);
    const { data: line } = order.addPaymentline(method);
    return { store, order, method, line };
};

const captureCalls = (response) => {
    const calls = [];
    onRpc("pos.payment.method", "stripe_capture_payment", ({ args }) => {
        calls.push(args[0]);
        return response;
    });
    return calls;
};

describe("capture after payment", () => {
    test("a failed capture leaves the line to retry instead of done", async () => {
        const calls = captureCalls({ error: { message: "card_declined" } });
        const { line } = await setupStripeLine();

        const isPaymentSuccessful = await line.pay();

        expect(calls).toEqual(["pi_AUTH"]);
        expect(isPaymentSuccessful).toBe(false);
        expect(line.getPaymentStatus()).toBe("retry");
    });

    test("a captured payment marks the line done", async () => {
        const calls = captureCalls({ id: "pi_AUTH", charges: false });
        const { line } = await setupStripeLine();

        expect(await line.pay()).toBe(true);
        expect(calls).toEqual(["pi_AUTH"]);
        expect(line.getPaymentStatus()).toBe("done");
        expect(line.transaction_id).toBe("pi_AUTH");
    });
});

describe("reload while waiting for capture", () => {
    const reload = async ({ store, method, line }) => {
        store.selectedOrderUuid = null;
        method.payment_terminal = new PaymentStripe(store, method);
        await waitUntil(() => line.getPaymentStatus() !== "waitingCapture");
    };

    test("the authorized intent is captured when the terminal comes back", async () => {
        const calls = captureCalls({ id: "pi_RELOADED", charges: false });
        const setup = await setupStripeLine();
        setup.line.transaction_id = "pi_RELOADED";
        setup.line.setPaymentStatus("waitingCapture");

        await reload(setup);

        expect(calls).toEqual(["pi_RELOADED"]);
        expect(setup.line.getPaymentStatus()).toBe("done");
    });

    test("an unconfirmed capture is left to the cashier, never retried", async () => {
        const calls = captureCalls({ error: { message: "already captured" } });
        const setup = await setupStripeLine();
        setup.line.transaction_id = "pi_RELOADED";
        setup.line.setPaymentStatus("waitingCapture");

        await reload(setup);

        expect(calls).toEqual(["pi_RELOADED"]);
        expect(setup.line.getPaymentStatus()).toBe("force_done");
    });
});
