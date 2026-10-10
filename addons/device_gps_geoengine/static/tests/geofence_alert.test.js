/** @odoo-module native */
import "@device_gps_geoengine/geoengine_gps_live";

import { GeoengineRenderer } from "@geoengine/geoengine/geoengine_renderer";
import { describe, expect, test } from "@odoo/hoot";

describe.current.tags("headless");

function renderer(resModel) {
    return Object.assign(Object.create(GeoengineRenderer.prototype), {
        props: { model: { root: { resModel } } },
        notification: {
            add: (message, options) => expect.step(`${options.type}: ${message}`),
        },
    });
}

test("the devices map says when a device crosses a geofence", () => {
    const map = renderer("device.device");
    map._onGeofenceAlert({
        type: "geofence_enter",
        device_name: "Truck 7",
        geofence_name: "Yard",
    });
    map._onGeofenceAlert({
        type: "geofence_exit",
        device_name: "Truck 7",
        geofence_name: "Yard",
    });
    expect.verifySteps(["info: Truck 7 entered Yard", "info: Truck 7 left Yard"]);
});

test("a map of something else stays quiet", () => {
    renderer("geo.site")._onGeofenceAlert({
        type: "geofence_enter",
        device_name: "Truck 7",
        geofence_name: "Yard",
    });
    expect.verifySteps([]);
});
