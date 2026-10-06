import { expect, test } from "@odoo/hoot";
import { getFilledOrder } from "@point_of_sale/../tests/unit/utils";
import { definePosPrepDisplayModels } from "@pos_enterprise/../tests/unit/data/generate_model_definitions";
import { setupPosEnvForPrepDisplay } from "@pos_enterprise/../tests/unit/utils";

definePosPrepDisplayModels();

test("sendOrderInPreparation", async () => {
    const store = await setupPosEnvForPrepDisplay();
    const order = await getFilledOrder(store);

    expect(store.getPendingOrder().orderToCreate).toHaveLength(1);
    expect(order.lines[0].uiState.savedQuantity).toBe(0);
    expect(order.lines[1].uiState.savedQuantity).toBe(0);

    await store.sendOrderInPreparation(order);
    expect(store.getPendingOrder().orderToCreate).toHaveLength(0);
    expect(order.lines).toHaveLength(2);
    expect(order.lines[0].id).toBeOfType("number");
    expect(order.lines[1].id).toBeOfType("number");
    expect(order.lines[0].uiState.savedQuantity).toBe(3);
    expect(order.lines[1].uiState.savedQuantity).toBe(2);
});
