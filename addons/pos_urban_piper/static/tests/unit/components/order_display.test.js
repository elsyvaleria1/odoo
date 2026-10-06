import { expect, test } from "@odoo/hoot";
import { OrderDisplay } from "@point_of_sale/app/components/order_display/order_display";
import { setupPosEnvForPrepDisplay } from "@pos_enterprise/../tests/unit/utils";
import { getUrbanPiperFilledOrder } from "@pos_urban_piper/../tests/unit/utils";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { now } from "@web/core/l10n/dates";

import { definePosUrbanPiperModels } from "../data/generate_model_definitions.js";

definePosUrbanPiperModels();

test("showTimer and _computeRemainingTime", async () => {
    const store = await setupPosEnvForPrepDisplay();
    const order = await getUrbanPiperFilledOrder(store);
    const comp = await mountWithCleanup(OrderDisplay, {
        props: {
            orderAcceptTime: now().epochMilliseconds,
            orderPrepTime: 15,
            order,
            slots: {},
        },
    });
    expect(comp.showTimer).toBe(true);
    expect(comp._computeRemainingTime()).toBe(15);

    order.state = "paid";
    const comp2 = await mountWithCleanup(OrderDisplay, {
        props: {
            orderAcceptTime: now().epochMilliseconds,
            orderPrepTime: 15,
            order,
            slots: {},
        },
    });
    expect(comp2.showTimer).toBeEmpty();
    expect(comp2._computeRemainingTime()).toBeEmpty();
});
