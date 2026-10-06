import { expect, test } from "@odoo/hoot";
import { setupPosEnvForPrepDisplay } from "@pos_enterprise/../tests/unit/utils";

import { definePosUrbanPiperModels } from "../data/generate_model_definitions.js";

definePosUrbanPiperModels();

function cachedRows(deliveryIdentifier) {
    return {
        "pos.order": [
            { id: 1, uuid: "o1", delivery_identifier: deliveryIdentifier },
            { id: 2, uuid: "o2", delivery_identifier: false },
        ],
        "pos.order.line": [
            { uuid: "l1", order_id: 1 },
            { uuid: "l2", order_id: 2 },
        ],
        "pos.payment": [
            { uuid: "p1", pos_order_id: 1 },
            { uuid: "p2", pos_order_id: 2 },
        ],
    };
}

test("restoring the local cache drops delivery orders and their lines and payments", async () => {
    const store = await setupPosEnvForPrepDisplay();

    const restored = await store.data.preLoadData(cachedRows("OID001"));

    expect(restored["pos.order"].map((o) => o.uuid)).toEqual(["o2"]);
    expect(restored["pos.order.line"].map((l) => l.uuid)).toEqual(["l2"]);
    expect(restored["pos.payment"].map((p) => p.uuid)).toEqual(["p2"]);
});

test("restoring the local cache keeps every order that is not a delivery", async () => {
    const store = await setupPosEnvForPrepDisplay();

    const restored = await store.data.preLoadData(cachedRows(false));

    expect(restored["pos.order"].map((o) => o.uuid)).toEqual(["o1", "o2"]);
    expect(restored["pos.order.line"].map((l) => l.uuid)).toEqual(["l1", "l2"]);
    expect(restored["pos.payment"].map((p) => p.uuid)).toEqual(["p1", "p2"]);
});
