/** @odoo-module native */
import { GeoengineRendererInteractions } from "@geoengine/geoengine/renderer/geoengine_renderer_interactions";
import { beforeEach, describe, expect, test } from "@odoo/hoot";

describe.current.tags("headless");

function makeRenderer() {
    return {
        overlay: {
            position: [0, 0],
            setPosition(value) {
                this.position = value;
            },
        },
        record: { resId: 7 },
        state: { popup: { key: 3, record: { resId: 7 } } },
        props: { model: { root: { resModel: "geo.record" } } },
    };
}

describe("geoengine popup lifecycle", () => {
    let renderer;
    let interactions;

    beforeEach(() => {
        renderer = makeRenderer();
        interactions = new GeoengineRendererInteractions(renderer);
    });

    test("hiding the popup unmounts the record component and releases the record", () => {
        interactions.hidePopup();

        expect(renderer.overlay.position).toBe(undefined, {
            message: "the overlay is moved off the map",
        });
        expect(renderer.state.popup).toBe(null, {
            message:
                "the popup is a child of the renderer's template now, gated on " +
                "state.popup; clearing the state is what unmounts it. It used to be " +
                "a second Owl App mounted by hand, which leaked when a popup was " +
                "closed and no other opened.",
        });
        expect(renderer.record).toBe(null);
    });

    test("hiding a popup that was never opened is harmless", () => {
        renderer.state.popup = null;
        renderer.record = null;
        expect(() => interactions.hidePopup()).not.toThrow();
        expect(renderer.overlay.position).toBe(undefined);
    });

    test("every mount gets a new key, so a popup for another record remounts", () => {
        interactions.mountGeoengineRecord({
            archInfo: {},
            templateDocs: {},
            model: null,
            attributes: { id: 9, name: "nine" },
            resModel: "geo.record",
        });
        expect(renderer.state.popup.key).toBe(4);
        expect(renderer.state.popup.record.resId).toBe(9);
        expect(renderer.state.popup.record.resModel).toBe("geo.record");
    });
});
