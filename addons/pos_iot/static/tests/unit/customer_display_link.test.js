import { expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosIotModels } from "./data/generate_model_definitions.js";

definePosIotModels();

test("a revoked display link reopens the IoT box's display with the new one", async () => {
    onRpc("/hw_drivers/action", () => true);
    onRpc("/iot_drivers/event", () => true);
    patchWithCleanup(console, { log: () => {} });
    onRpc("/css", () => "");
    onRpc("/fonts/*", () => "");
    onRpc("/point_of_sale/static/*", () => "");
    onRpc("/web/static/*", () => "");

    const store = await setupPosEnv();
    const sent = [];
    patchWithCleanup(store.iotHttp, {
        action: (iotId, identifier, data) => sent.push({ identifier, data }),
    });

    store.customerDisplayTokenNotification({ token: "new-display-link" });

    expect(store.config.customer_display_token).toBe("new-display-link");
    expect(sent).toEqual([
        {
            identifier: "display_identifier",
            data: {
                action: "open",
                access_token: "new-display-link",
                pos_id: store.config.id,
            },
        },
    ]);
});
