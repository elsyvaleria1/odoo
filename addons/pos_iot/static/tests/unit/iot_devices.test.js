import { expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";

import { definePosIotModels } from "./data/generate_model_definitions.js";

definePosIotModels();

test("pos_iot_common", async () => {
    onRpc("/hw_drivers/action", () => true);
    onRpc("/iot_drivers/event", () => true);
    patchWithCleanup(console, { log: () => {} });

    onRpc("/css", () => "");
    onRpc("/fonts/*", () => "");
    onRpc("/point_of_sale/static/*", () => "");
    onRpc("/web/static/*", () => "");

    const store = await setupPosEnv();
    const hardwareProxy = store.hardwareProxy;
    const iotBoxes = hardwareProxy.iotBoxes;

    expect(iotBoxes).toHaveLength(1);
    expect(iotBoxes[0].name).toBe("DEMO IOT BOX");
    expect(iotBoxes[0].ip).toBe("1.1.1.1");
    expect(store.config.useProxy).toBe(true);

    expect(hardwareProxy.iotBoxes[0].connected).toBeEmpty();
    await hardwareProxy.setProxyConnectionStatus("1.1.1.1", true);
    expect(hardwareProxy.connectionInfo.status).toBe("connected");
    expect(hardwareProxy.iotBoxes[0].connected).toBe(true);

    expect(Object.keys(hardwareProxy.deviceControllers)).toEqual([
        "printer",
        "display",
        "scanners",
        "scale",
    ]);
    expect(store.scale._scaleDevice).not.toBeEmpty();

    expect(store.unwatched.printers).toHaveLength(2);
    expect(hardwareProxy.printer).not.toBeEmpty();
    const hardwareProxyPrinter = hardwareProxy.printer.device;
    expect(hardwareProxyPrinter.id).toInclude("listener");
    expect(hardwareProxyPrinter.identifier).toBe("printer_identifier");

    await hardwareProxy.setProxyConnectionStatus("1.1.1.1", false);
    expect(hardwareProxy.iotBoxes[0].connected).toBe(false);
    expect(hardwareProxy.connectionInfo.status).toBe("disconnected");
    expect(hardwareProxy.connectionInfo.message).toBe("DEMO IOT BOX disconnected");
});
