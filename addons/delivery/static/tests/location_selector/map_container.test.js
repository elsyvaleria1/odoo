import { MapContainer } from "@delivery/js/location_selector/map_container/map_container";
import { describe, expect, test } from "@odoo/hoot";
import { waitFor } from "@odoo/hoot-dom";
import { mountWithCleanup, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { leafletLoader } from "@web/core/lib/leaflet";

describe.current.tags("desktop");

const props = {
    locations: [
        {
            id: 1,
            name: "Pick-up point",
            street: "Rue du Marché 1",
            city: "Brussels",
            zip_code: "1000",
            latitude: 50.85,
            longitude: 4.35,
            opening_hours: {},
        },
    ],
    selectedLocationId: false,
    setSelectedLocation: () => {},
    validateSelection: () => {},
};

test("the map draws once Leaflet and its stylesheet loaded", async () => {
    // Leaflet draws layers only once the map has a view, which the selected
    // location gives it
    await mountWithCleanup(MapContainer, {
        props: { ...props, selectedLocationId: "1" },
    });
    await waitFor(".o_location_selector_map.leaflet-container");
    expect(".leaflet-marker-icon").toHaveCount(1);
});

test("a Leaflet module that fails to import leaves the selector usable", async () => {
    // what a failed import() rejects with; the old catch only knew loadJS's error
    patchWithCleanup(leafletLoader, {
        load: () =>
            Promise.reject(
                new TypeError("Failed to fetch dynamically imported module"),
            ),
    });
    await mountWithCleanup(MapContainer, { props });
    await waitFor(".bg-200 span");
    expect(".bg-200 span").toHaveText("There was an error loading the map");
    expect(".o_location_selector_map").toHaveCount(0);
});
