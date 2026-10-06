import { describe, expect, test } from "@odoo/hoot";
import { setupPosEnvForPrepDisplay } from "@pos_enterprise/../tests/unit/utils";

import { definePosUrbanPiperModels } from "../data/generate_model_definitions.js";

definePosUrbanPiperModels();

describe("pos_store", () => {
    test("onDeleteOrder", async () => {
        const store = await setupPosEnvForPrepDisplay();
        const order = store.addNewOrder();

        order.delivery_identifier = "UP-123";
        let deletedOrder = await store.onDeleteOrder(order);
        expect(deletedOrder).toBe(false);
        expect(order.uiState.displayed).toBe(true);

        order.delivery_identifier = undefined;
        deletedOrder = await store.onDeleteOrder(order);
        expect(deletedOrder).toBe(true);
        expect(order.uiState.displayed).toBe(false);
    });
});
