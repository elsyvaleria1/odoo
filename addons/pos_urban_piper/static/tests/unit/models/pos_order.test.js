import { expect, test } from "@odoo/hoot";
import { setupPosEnvForPrepDisplay } from "@pos_enterprise/../tests/unit/utils";
import { getUrbanPiperFilledOrder } from "@pos_urban_piper/../tests/unit/utils";

import { definePosUrbanPiperModels } from "../data/generate_model_definitions.js";

definePosUrbanPiperModels();

test("getDeliveryProviderName, isFutureOrder, isDirectSale, deliveryOrderType, getOrderStatus, getProviderOrderId", async () => {
    const store = await setupPosEnvForPrepDisplay();
    const order = await getUrbanPiperFilledOrder(store);
    order.delivery_status = "food_ready";
    expect(order.getDeliveryProviderName()).toEqual("DoorDash");
    expect(order.getOrderStatus()).toEqual("food_ready");
    expect(order.isDirectSale).toEqual(false);
    expect(order.deliveryOrderType).toEqual("partner");
    expect(order.isFutureOrder()).toEqual(false);
    expect(order.getProviderOrderId).toEqual("TST-1756819673");
});
