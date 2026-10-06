// @ts-check
import { DevicesTile } from "@device/home_tile/devices_tile";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts } from "@odoo/hoot-dom";
import {
    contains,
    mockService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("the devices tile counts the states and opens the silent devices", async () => {
    mockService("action", {
        async doAction(/** @type {any} */ action, /** @type {any} */ options) {
            expect.step(
                typeof action === "string"
                    ? `${action} ${JSON.stringify(options?.additionalContext ?? {})}`
                    : `${action.res_model} ${action.res_id}`,
            );
        },
    });
    await mountWithCleanup(DevicesTile, {
        props: {
            data: {
                connected: 7,
                disconnected: 2,
                error: 1,
                devices: [
                    {
                        id: 3,
                        name: "Truck 12",
                        state: "error",
                        last_data: "2026-09-25 08:00:00",
                    },
                    {
                        id: 4,
                        name: "Tractor 2",
                        state: "disconnected",
                        last_data: false,
                    },
                ],
            },
            size: "1x1",
        },
    });
    expect(queryAllTexts(".o_devices_tile_totals strong")).toEqual(["7", "2", "1"]);
    expect(".o_devices_tile_device:first .fa-exclamation-circle").toHaveCount(1);
    expect(".o_devices_tile_device:last small").toHaveText("Never reported");

    expect(".o_devices_tile_device:first").toHaveAttribute(
        "href",
        "/odoo/device.device/3",
    );
    await contains(".o_devices_tile_device:first").click();
    await contains(".o_devices_tile_totals button:eq(0)").click();
    await contains(".o_devices_tile_totals button:eq(2)").click();
    expect.verifySteps([
        "device.device 3",
        'device.action_device_device {"search_default_filter_connected":1}',
        'device.action_device_device {"search_default_filter_error":1}',
    ]);
});

test("every device reporting says so", async () => {
    await mountWithCleanup(DevicesTile, {
        props: {
            data: { connected: 3, disconnected: 0, error: 0, devices: [] },
            size: "1x1",
        },
    });
    expect(".o_devices_tile p").toHaveText("Every device is reporting.");
});
