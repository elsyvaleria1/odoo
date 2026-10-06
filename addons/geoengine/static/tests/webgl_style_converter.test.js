/** @odoo-module native */
import { INTERVAL, UNIQUE } from "@geoengine/geoengine/classification";
import {
    createChoroplethExpression,
    createProportionalSizeExpression,
    createWebGLStyle,
    createWebGLStyleWithHighlight,
    detectGeometryType,
} from "@geoengine/geoengine/renderer/webgl_style_converter";
import { describe, expect, test } from "@odoo/hoot";

function operatorsIn(expression) {
    const found = new Set();
    const walk = (node) => {
        if (!Array.isArray(node)) {
            return;
        }
        if (typeof node[0] === "string") {
            found.add(node[0]);
        }
        node.forEach(walk);
    };
    walk(expression);
    return found;
}

const SUPPORTED_OPERATORS = new Set([
    "get",
    "var",
    "case",
    "match",
    "interpolate",
    "linear",
    "==",
    "<=",
    "<",
    ">=",
    ">",
    "has",
    "line-metric",
]);

const INTERVAL_STYLING = {
    mode: INTERVAL,
    values: [0, 7395.75, 14791.5, 22187.25, 29583],
    colors: [
        "rgba(255, 104, 10, 0.8)",
        "rgba(170, 104, 10, 0.8)",
        "rgba(85, 104, 10, 0.8)",
        "rgba(0, 104, 10, 0.8)",
    ],
};

describe("createChoroplethExpression", () => {
    test("uses only operators OpenLayers 10.7 actually has", () => {
        const expr = createChoroplethExpression(INTERVAL_STYLING, "score");
        expect(operatorsIn(expr).has("step")).toBe(false);
        for (const op of operatorsIn(expr)) {
            expect(SUPPORTED_OPERATORS.has(op)).toBe(true);
        }
    });

    test("builds one branch per class boundary, ending in the last class", () => {
        const expr = createChoroplethExpression(INTERVAL_STYLING, "score");
        expect(expr[0]).toBe("case");
        expect(expr.length).toBe(8);
        expect(expr.at(-1)).toBe("rgba(0, 104, 10, 0.8)");
    });

    test("categorical classifications become a match, not a range test", () => {
        const expr = createChoroplethExpression(
            { mode: UNIQUE, values: [1, 2], colors: ["a", "b"] },
            "score",
        );
        expect(expr[0]).toBe("match");
        expect(expr.slice(2)).toEqual([1, "a", 2, "b", "rgba(204, 204, 204, 0.55)"]);
    });

    test("refuses a classification a shader cannot express", () => {
        expect(
            createChoroplethExpression(
                { mode: UNIQUE, values: ["draft"], colors: ["a"] },
                "state",
            ),
        ).toBe(null);
    });

    test("refuses an empty or absent classification", () => {
        expect(createChoroplethExpression({}, "score")).toBe(null);
        expect(createChoroplethExpression(INTERVAL_STYLING, undefined)).toBe(null);
    });
});

describe("createWebGLStyle", () => {
    test("a basic layer renders, with opacity baked into the colour", () => {
        const { style } = createWebGLStyle(
            { geo_repr: "basic", layer_opacity: 0.5 },
            null,
            "polygon",
        );
        expect(style["fill-color"]).toBe("rgba(51, 136, 255, 0.5)");
    });

    test("a choropleth layer renders without a step operator", () => {
        const { style } = createWebGLStyle(
            { geo_repr: "colored", attribute_field_name: "score" },
            INTERVAL_STYLING,
            "polygon",
        );
        expect(operatorsIn(style["fill-color"]).has("step")).toBe(false);
    });

    test("colored_field is reported unsupported instead of failing to compile", () => {
        const result = createWebGLStyle(
            { geo_repr: "colored_field", color_field_name: "colour" },
            null,
            "polygon",
        );
        expect(result.unsupported).toBe(true);
        expect(typeof result.reason).toBe("string");
    });

    test("an inexpressible choropleth is reported unsupported", () => {
        const result = createWebGLStyle(
            { geo_repr: "colored", attribute_field_name: "state" },
            { mode: UNIQUE, values: ["draft"], colors: ["a"] },
            "polygon",
        );
        expect(result.unsupported).toBe(true);
    });

    test("a line layer strokes with the fill expression", () => {
        const { style } = createWebGLStyle({ geo_repr: "basic" }, null, "linestring");
        expect(style["stroke-color"]).toBe("rgba(51, 136, 255, 1)");
        expect(style["fill-color"]).toBe(undefined);
    });
});

describe("createWebGLStyleWithHighlight", () => {
    test("wraps the colour in a highlight case", () => {
        const { style, variables } = createWebGLStyleWithHighlight(
            { geo_repr: "basic" },
            null,
            "polygon",
        );
        expect(style["fill-color"][0]).toBe("case");
        expect(variables.highlightedId).toBe(-1);
    });

    test("passes an unsupported verdict straight through", () => {
        const result = createWebGLStyleWithHighlight(
            { geo_repr: "colored_field" },
            null,
            "polygon",
        );
        expect(result.unsupported).toBe(true);
        expect(result.style).toBe(undefined);
    });
});

describe("createProportionalSizeExpression", () => {
    test("interpolates between the configured sizes", () => {
        const expr = createProportionalSizeExpression(
            { minValue: 0, maxValue: 100, minSize: 5, maxSize: 15 },
            "score",
        );
        expect(expr).toEqual([
            "interpolate",
            ["linear"],
            ["get", "score"],
            0,
            5,
            100,
            15,
        ]);
    });

    test("collapses to a single radius when every value is the same", () => {
        expect(
            createProportionalSizeExpression(
                { minValue: 7, maxValue: 7, minSize: 5, maxSize: 15 },
                "score",
            ),
        ).toBe(10);
    });
});

describe("detectGeometryType", () => {
    test("reads the type off the first feature's geometry", () => {
        const data = [{ the_geom: '{"type": "MultiPoint", "coordinates": []}' }];
        expect(detectGeometryType({ geo_field_name: "the_geom" }, data)).toBe("point");
    });

    test("falls back to polygon with nothing to go on", () => {
        expect(detectGeometryType({ geo_field_name: "the_geom" }, [])).toBe("polygon");
    });
});

describe("label styling", () => {
    const labelled = {
        geo_repr: "basic",
        display_polygon_labels: true,
        attribute_field_name: "yield_t",
    };

    test("emits the text-* properties when the layer asks for labels", () => {
        const { style } = createWebGLStyle(labelled, null, "polygon");

        expect(style["text-value"]).toEqual(["get", "label"]);
        expect(style["text-font"]).toBe("12px Calibri,sans-serif");
        expect(style["text-fill-color"]).toBe("#000");
        expect(style["text-stroke-color"]).toBe("#fff");
        expect(style["text-stroke-width"]).toBe(2);
    });

    test("stays silent when labels are off", () => {
        const { style } = createWebGLStyle(
            { ...labelled, display_polygon_labels: false },
            null,
            "polygon",
        );
        expect(style["text-value"]).toBe(undefined);
    });

    test("stays silent when the layer names no field to label with", () => {
        const { style } = createWebGLStyle(
            { ...labelled, attribute_field_name: false },
            null,
            "polygon",
        );
        expect(style["text-value"]).toBe(undefined);
    });

    test("labels points and lines too, not only polygons", () => {
        for (const geometryType of ["point", "line", "polygon"]) {
            const { style } = createWebGLStyle(labelled, null, geometryType);
            expect(style["text-value"]).toEqual(["get", "label"]);
        }
    });

    test("survives the highlight wrapper, which only touches colours", () => {
        const { style } = createWebGLStyleWithHighlight(labelled, null, "polygon");
        expect(style["text-value"]).toEqual(["get", "label"]);
        expect(style["fill-color"][0]).toBe("case");
    });

    test("a colour classification WebGL cannot express reports unsupported, labels or not", () => {
        const result = createWebGLStyle(
            { ...labelled, geo_repr: "colored_field", color_field_name: "colour" },
            null,
            "polygon",
        );
        expect(result.unsupported).toBe(true);
        expect(result.style).toBe(undefined);
    });
});
