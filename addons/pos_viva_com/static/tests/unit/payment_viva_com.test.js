import { beforeEach, expect, test } from "@odoo/hoot";
import { definePosModels } from "@point_of_sale/../tests/unit/data/generate_model_definitions";
import { PosConfig } from "@point_of_sale/../tests/unit/data/pos_config.data";
import { PosPaymentMethod } from "@point_of_sale/../tests/unit/data/pos_payment_method.data";
import { getFilledOrder, setupPosEnv } from "@point_of_sale/../tests/unit/utils";

definePosModels();

const VIVA_METHOD_ID = 16;

beforeEach(() => {
    PosPaymentMethod._records = [
        ...PosPaymentMethod._records,
        {
            id: VIVA_METHOD_ID,
            name: "Viva",
            is_cash_count: false,
            use_payment_terminal: "viva_com",
            split_transactions: false,
            type: "bank",
            image: false,
            sequence: 3,
            payment_method_type: "terminal",
            default_qr: false,
            viva_com_terminal_id: "T1",
        },
    ];
    PosConfig._records = PosConfig._records.map((config) => ({
        ...config,
        payment_method_ids: [...config.payment_method_ids, VIVA_METHOD_ID],
    }));
});

test("the session id outlives a server update of the line, so its result still lands", async () => {
    const store = await setupPosEnv();
    const order = await getFilledOrder(store);
    const method = store.models["pos.payment.method"].get(VIVA_METHOD_ID);
    const { data: line } = order.addPaymentline(method);
    line.setPaymentStatus("waitingCard");
    line.uiState.vivaSessionId = `${order.uuid} - session`;

    store.models.loadConnectedData(
        { "pos.payment": [{ ...line.raw, id: 4242, payment_status: "waitingCard" }] },
        [],
    );

    expect(line.uiState.vivaSessionId).toBe(`${order.uuid} - session`);
    store.data.channels
        .find(({ channel }) => channel === "VIVA_COM_LATEST_RESPONSE")
        .method({
            config_id: store.config.id,
            session_id: `${order.uuid} - session`,
            success: true,
            transaction_id: "viva-1",
        });
    expect(line.getPaymentStatus()).toBe("done");
    expect(line.transaction_id).toBe("viva-1");
});
