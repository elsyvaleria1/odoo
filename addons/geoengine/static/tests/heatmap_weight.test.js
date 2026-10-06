/** @odoo-module native */

import { makeHeatmapWeight } from "@geoengine/geoengine/renderer/geoengine_renderer_layers";
import { describe, expect, test } from "@odoo/hoot";

function featureFor(record) {
    return { get: (key) => (key === "record" ? record : undefined) };
}

const rows = [{ tonnage: 2 }, { tonnage: 8 }, { tonnage: 4 }];

describe("makeHeatmapWeight", () => {
    test("weights every point equally when no field is named", () => {
        const weight = makeHeatmapWeight(rows, false);
        expect(weight(featureFor({ tonnage: 2 }))).toBe(1);
        expect(weight(featureFor({ tonnage: 8 }))).toBe(1);
    });

    test("normalises against the layer maximum, not the raw value", () => {
        const weight = makeHeatmapWeight(rows, "tonnage");
        expect(weight(featureFor({ tonnage: 8 }))).toBe(1);
        expect(weight(featureFor({ tonnage: 4 }))).toBe(0.5);
        expect(weight(featureFor({ tonnage: 2 }))).toBe(0.25);
    });

    test("clamps a value above the maximum it was built from", () => {
        const weight = makeHeatmapWeight(rows, "tonnage");
        expect(weight(featureFor({ tonnage: 80 }))).toBe(1);
    });

    test("falls back to uniform weighting when nothing is positive", () => {
        const weight = makeHeatmapWeight([{ tonnage: 0 }, { tonnage: 0 }], "tonnage");
        expect(weight(featureFor({ tonnage: 0 }))).toBe(1);
    });

    test("falls back to uniform weighting for a field that is not numeric", () => {
        const weight = makeHeatmapWeight([{ label: "a" }, { label: "b" }], "label");
        expect(weight(featureFor({ label: "a" }))).toBe(1);
    });

    test("gives a negative or unreadable value no weight at all", () => {
        const weight = makeHeatmapWeight(rows, "tonnage");
        expect(weight(featureFor({ tonnage: -5 }))).toBe(0);
        expect(weight(featureFor({}))).toBe(0);
    });
});
