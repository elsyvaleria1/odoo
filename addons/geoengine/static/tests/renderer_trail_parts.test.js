/** @odoo-module native */
import { TrailLayerBuilder } from "@geoengine/geoengine/renderer/trail_layer";
import { describe, expect, test } from "@odoo/hoot";

const layers = Object.create(TrailLayerBuilder.prototype);
const geom = (type, coordinates) => ({
    getType: () => type,
    getCoordinates: () => coordinates,
});

describe("WebGL trail geometry parts", () => {
    test("a plain LineString is one part", () => {
        expect(
            layers._trailParts(
                geom("LineString", [
                    [0, 0],
                    [1, 1],
                    [2, 2],
                ]),
            ),
        ).toEqual([
            [
                [0, 0],
                [1, 1],
                [2, 2],
            ],
        ]);
    });

    test("a MultiLineString keeps every part, in order", () => {
        const parts = [
            [
                [0, 0],
                [1, 1],
            ],
            [
                [5, 5],
                [6, 6],
                [7, 7],
            ],
        ];
        expect(layers._trailParts(geom("MultiLineString", parts))).toEqual(parts);
    });

    test("degenerate single-vertex parts are dropped", () => {
        expect(
            layers._trailParts(
                geom("MultiLineString", [
                    [[0, 0]],
                    [
                        [1, 1],
                        [2, 2],
                    ],
                ]),
            ),
        ).toEqual([
            [
                [1, 1],
                [2, 2],
            ],
        ]);
    });

    test("a geometry that is not a line yields no parts", () => {
        expect(layers._trailParts(geom("Point", [0, 0]))).toEqual([]);
        expect(layers._trailParts(geom("Polygon", [[[0, 0]]]))).toEqual([]);
    });
});

describe("WebGL trail timestamp interpolation", () => {
    test("stretches a short series across every vertex", () => {
        const out = layers._interpolateTimestamps([100, 200], 5);
        expect(out.length).toBe(5);
        expect(out[0]).toBe(100);
        expect(out.at(-1)).toBe(200);
        expect(out.every((v, i, a) => i === 0 || v >= a[i - 1])).toBe(true);
    });

    test("leaves a series that already matches alone", () => {
        expect(layers._interpolateTimestamps([1, 2, 3], 3)).toEqual([1, 2, 3]);
    });

    test("fills from a single reading", () => {
        expect(layers._interpolateTimestamps([42], 3)).toEqual([42, 42, 42]);
    });
});
