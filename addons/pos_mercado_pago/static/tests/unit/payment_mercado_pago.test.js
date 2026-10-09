import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { advanceTime } from "@odoo/hoot-mock";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PaymentMercadoPago } from "@pos_mercado_pago/app/utils/payment/payment_mercado_pago";
import { mountWithCleanup, onRpc } from "@web/../tests/web_test_helpers";

definePosModels();

const MP_METHOD_ID = 12;

beforeEach(() => {
    PosPaymentMethod._records = [
        ...PosPaymentMethod._records,
        {
            id: MP_METHOD_ID,
            name: "Mercado Pago",
            is_cash_count: false,
            use_payment_terminal: "mercado_pago",
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
        payment_method_ids: [...config.payment_method_ids, MP_METHOD_ID],
    }));
    onRpc("/css", () => "");
    onRpc("/fonts/*", () => "");
    onRpc("/web/static/*", () => "");
});

const mercadoPago = () => {
    const state = { intent: "OPEN", payment: "approved", created: [], cancels: 0 };
    onRpc("pos.payment.method", "mp_payment_intent_create", ({ args }) => {
        state.created.push(args[1]);
        return { id: "intent-1" };
    });
    onRpc("pos.payment.method", "mp_payment_intent_get", ({ args }) => ({
        id: args[1],
        state: state.intent,
        payment: { id: 99 },
    }));
    onRpc("pos.payment.method", "mp_get_payment_status", ({ args }) => {
        state.paymentLookups = [...(state.paymentLookups ?? []), args[1]];
        return { status: state.payment };
    });
    onRpc("pos.payment.method", "mp_payment_intent_cancel", () => {
        state.cancels++;
        return { error: "on terminal", status: 409 };
    });
    return state;
};

const setupLine = async (amount = 10) => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(MP_METHOD_ID);
    const { data: line } = order.addPaymentline(method);
    line.setAmount(amount);
    return { store, order, method, line };
};

const notifyWebhook = (store) =>
    store.data.channels
        .find(({ channel }) => channel === "MERCADO_PAGO_LATEST_MESSAGE")
        .method({ config_id: store.config.id });

describe("amount", () => {
    test("the payment intent asks for the amount in cents, rounded", async () => {
        const state = mercadoPago();
        const { line } = await setupLine(19.99);

        line.pay();
        await waitUntil(() => line.getPaymentStatus() === "waitingCard");

        expect(state.created.map((infos) => infos.amount)).toEqual([1999]);
    });
});

describe("late result", () => {
    test("the line keeps waiting while the terminal holds the intent, then accepts the late approval", async () => {
        const state = mercadoPago();
        const { store, line } = await setupLine();
        const payment = line.pay();
        await waitUntil(() => line.getPaymentStatus() === "waitingCard");

        state.intent = "ON_TERMINAL";
        await notifyWebhook(store);
        await advanceTime(60000);
        expect(line.getPaymentStatus()).toBe("waitingCard");

        state.intent = "FINISHED";
        await notifyWebhook(store);

        expect(await payment).toBe(true);
        expect(line.getPaymentStatus()).toBe("done");
        expect(state.paymentLookups).toEqual(["intent-1"]);
    });

    test("polling settles the line when the webhook never arrives", async () => {
        const state = mercadoPago();
        const { line } = await setupLine();
        const payment = line.pay();
        await waitUntil(() => line.getPaymentStatus() === "waitingCard");

        state.intent = "FINISHED";
        await advanceTime(5000);

        expect(await payment).toBe(true);
        expect(line.getPaymentStatus()).toBe("done");
    });

    test("a rejected payment is a failure", async () => {
        const state = mercadoPago();
        const { store, line } = await setupLine();
        const payment = line.pay();
        await waitUntil(() => line.getPaymentStatus() === "waitingCard");

        state.intent = "FINISHED";
        state.payment = "rejected";
        await notifyWebhook(store);

        expect(await payment).toBe(false);
        expect(line.getPaymentStatus()).toBe("retry");
    });

    test("a cancel the terminal refuses keeps the line waiting, and its approval still lands", async () => {
        const state = mercadoPago();
        const { store, order, line } = await setupLine();
        const payment = line.pay();
        await waitUntil(() => line.getPaymentStatus() === "waitingCard");
        state.intent = "ON_TERMINAL";
        const screen = await mountWithCleanup(PaymentScreen, {
            props: { orderUuid: order.uuid },
        });

        await screen.sendPaymentCancel(line);

        expect(state.cancels).toBe(1);
        expect(line.getPaymentStatus()).toBe("waitingCard");
        state.intent = "FINISHED";
        await notifyWebhook(store);
        expect(await payment).toBe(true);
        expect(line.getPaymentStatus()).toBe("done");
    });

    test("an approval that lands while the cancel is refused is kept", async () => {
        const state = mercadoPago();
        const { order, line } = await setupLine();
        const payment = line.pay();
        await waitUntil(() => line.getPaymentStatus() === "waitingCard");
        state.intent = "FINISHED";
        const screen = await mountWithCleanup(PaymentScreen, {
            props: { orderUuid: order.uuid },
        });

        await screen.sendPaymentCancel(line);

        expect(await payment).toBe(true);
        expect(line.getPaymentStatus()).toBe("done");
    });

    test("after a reload the line resumes from its persisted intent", async () => {
        const state = mercadoPago();
        const { store, method, line } = await setupLine();
        line.pay();
        await waitUntil(() => line.getPaymentStatus() === "waitingCard");
        const persisted = JSON.parse(line.serializeForIndexedDB().JSONuiState);
        expect(persisted.mercadoPagoIntentId).toBe("intent-1");

        state.intent = "FINISHED";
        method.payment_terminal = new PaymentMercadoPago(store, method);
        await waitUntil(() => line.getPaymentStatus() !== "waitingCard");

        expect(line.getPaymentStatus()).toBe("done");
    });
});
