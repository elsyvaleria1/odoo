import { beforeEach, expect, test } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";

definePosModels();

const RAZORPAY_METHOD_ID = 17;

beforeEach(() => {
    PosPaymentMethod._records = [
        ...PosPaymentMethod._records,
        {
            id: RAZORPAY_METHOD_ID,
            name: "Razorpay",
            is_cash_count: false,
            use_payment_terminal: "razorpay",
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
        payment_method_ids: [...config.payment_method_ids, RAZORPAY_METHOD_ID],
    }));
});

test("a refund line keeps the payment it refunds across a server update", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(RAZORPAY_METHOD_ID);
    const { data: line } = order.addPaymentline(method);
    line.updateRefundPaymentLine({
        transaction_id: "TXN1",
        razorpay_p2p_request_id: "P2P1",
    });

    store.models.loadConnectedData({ "pos.payment": [{ ...line.raw, id: 4243 }] }, []);

    expect(line.uiState.transaction_id).toBe("TXN1");
    expect(line.uiState.razorpay_p2p_request_id).toBe("P2P1");
});
