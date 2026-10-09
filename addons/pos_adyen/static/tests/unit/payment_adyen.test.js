import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PaymentAdyen } from "@pos_adyen/app/utils/payment/payment_adyen";
import {
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

definePosModels();

const ADYEN_METHOD_ID = 11;

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
        },
    ];
    PosConfig._records = PosConfig._records.map((config) => ({
        ...config,
        payment_method_ids: [...config.payment_method_ids, ADYEN_METHOD_ID],
    }));
    onRpc("/css", () => "");
    onRpc("/fonts/*", () => "");
    onRpc("/web/static/*", () => "");
});

const approval = (serviceId) => ({
    SaleToPOIResponse: {
        MessageHeader: { ServiceID: serviceId },
        PaymentResponse: {
            Response: {
                Result: "Success",
                AdditionalResponse: "pspReference=PSP9&cardType=visa",
            },
            PaymentResult: { AmountsResp: { AuthorizedAmount: 0, TipAmount: 0 } },
            PaymentReceipt: [],
        },
    },
});

const startAdyenPayment = async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(ADYEN_METHOD_ID);
    const sent = {};
    onRpc("pos.payment.method", "proxy_adyen_request", ({ args }) => {
        sent.serviceId = args[1].SaleToPOIRequest.MessageHeader.ServiceID;
        return true;
    });
    const { data: line } = order.addPaymentline(method);
    line.pay();
    await waitUntil(() => line.getPaymentStatus() === "waitingCard");
    return { store, order, method, line, sent };
};

const reloadFromIndexedDB = async (store, order) => {
    const data = store.data;
    const written = {};
    patchWithCleanup(data.indexedDB, {
        create: async (model, rows) => {
            for (const row of JSON.parse(JSON.stringify(rows))) {
                (written[model] ??= new Map()).set(row.uuid ?? row.id, row);
            }
            return rows.map(() => ({ status: "fulfilled" }));
        },
    });
    data.debouncedSynchronizeLocalDataInIndexedDB.cancel();
    await data._synchronizeLocalDataInIndexedDB();
    const rows = Object.fromEntries(
        ["pos.order", "pos.order.line", "pos.payment"].map((model) => [
            model,
            [...(written[model]?.values() ?? [])],
        ]),
    );
    data.localDeleteCascade(order);
    store.models.loadConnectedData(rows, []);
};

describe("reload while the terminal holds the payment", () => {
    test("the service id the terminal answers to survives the reload", async () => {
        const { store, order, line, sent } = await startAdyenPayment();
        expect(line.terminalServiceId).toBe(sent.serviceId);

        await reloadFromIndexedDB(store, order);

        const restored = store.models["pos.payment"].getBy("uuid", line.uuid);
        expect(restored).not.toBe(undefined);
        expect(restored.getPaymentStatus()).toBe("waitingCard");
        expect(restored.terminalServiceId).toBe(sent.serviceId);
    });

    test("an approval that arrives after the reload completes the line", async () => {
        const { store, order, method, line, sent } = await startAdyenPayment();
        await reloadFromIndexedDB(store, order);
        method.payment_terminal = new PaymentAdyen(store, method);
        onRpc("pos.payment.method", "get_latest_adyen_status", () =>
            approval(sent.serviceId),
        );

        await method.payment_terminal.handleAdyenStatusResponse();

        const restored = store.models["pos.payment"].getBy("uuid", line.uuid);
        expect(restored.getPaymentStatus()).toBe("done");
        expect(restored.transaction_id).toBe("PSP9");
    });

    test("an approval received while the page was down is picked up when the payment screen reopens", async () => {
        const { store, order, method, line, sent } = await startAdyenPayment();
        method.payment_terminal = new PaymentAdyen(store, method);
        onRpc("pos.payment.method", "get_latest_adyen_status", () =>
            approval(sent.serviceId),
        );

        await mountWithCleanup(PaymentScreen, { props: { orderUuid: order.uuid } });
        await waitUntil(() => line.getPaymentStatus() !== "waitingCard");

        expect(line.getPaymentStatus()).toBe("done");
        expect(line.transaction_id).toBe("PSP9");
    });

    test("an older payment's stored result does not settle the line on reopen", async () => {
        const { store, order, method, line } = await startAdyenPayment();
        method.payment_terminal = new PaymentAdyen(store, method);
        let polled = false;
        onRpc("pos.payment.method", "get_latest_adyen_status", () => {
            polled = true;
            return approval("0000000000");
        });

        await mountWithCleanup(PaymentScreen, { props: { orderUuid: order.uuid } });
        await waitUntil(() => polled);

        expect(line.getPaymentStatus()).toBe("waitingCard");
    });
});
