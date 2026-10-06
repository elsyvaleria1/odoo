/** @odoo-module native */

import { classColorFor, classValue, UNIQUE } from "@geoengine/geoengine/classification";
import { LayerClassifier } from "@geoengine/geoengine/layer_classifier";
import { loadGeoLibs } from "@geoengine/lib/geo_libs";
import { before, describe, expect, test, withFetch } from "@odoo/hoot";
import { globalCachedFetch } from "@web/../tests/_framework/module_set.hoot";

const record = (id, value) => ({
    resId: id,
    _values: { id, harvest: value, yield: value },
});

describe("classValue", () => {
    test("a record's date reads as the server sends it", () => {
        expect(classValue(Temporal.PlainDate.from("2026-03-01"))).toBe("2026-03-01");
    });

    test("an empty value classifies nothing", () => {
        expect(classValue(false)).toBe(null);
        expect(classValue("")).toBe(null);
        expect(classValue(0)).toBe(0);
    });
});

describe("LayerClassifier (production)", () => {
    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
    });

    const dateLayer = {
        resId: 1,
        name: "Harvests",
        geo_repr: "colored",
        classification: UNIQUE,
        attribute_field_name: "harvest",
        nb_class: 3,
    };

    test("dates on the drawn records match the population the server sends", () => {
        const data = [
            record(1, Temporal.PlainDate.from("2026-03-01")),
            record(2, Temporal.PlainDate.from("2026-04-01")),
        ];
        const styling = new LayerClassifier(null).classify(dateLayer, data, {
            values: ["2026-03-01", "2026-04-01", "2026-05-01"],
        });
        expect(classColorFor(styling, data[0]._values.harvest)).not.toBe(null);
        expect(classColorFor(styling, data[1]._values.harvest)).not.toBe(null);
    });

    test("an empty value is not a class of its own", () => {
        const styling = new LayerClassifier(null).classify(dateLayer, [
            record(1, "2026-03-01"),
            record(2, false),
        ]);
        expect(styling.values).toEqual(["2026-03-01"]);
    });

    test("each classification reads the population it is given", () => {
        const layer = {
            ...dateLayer,
            attribute_field_name: "yield",
            classification: "interval",
            nb_class: 2,
        };
        const classifier = new LayerClassifier(null);
        const data = [record(1, 5), record(2, 6)];
        const narrow = classifier.classify(layer, data, {
            bounds: { min: 0, max: 10 },
        });
        const wide = classifier.classify(layer, data, { bounds: { min: 0, max: 100 } });
        expect(narrow.values).toEqual([0, 5, 10]);
        expect(wide.values).toEqual([0, 50, 100]);
    });

    test("a transparent layer stays transparent", () => {
        const layer = { ...dateLayer, layer_opacity: 0 };
        const styling = new LayerClassifier(null).classify(layer, [record(1, "a")]);
        expect(styling.opacity).toBe(0);
    });
});

describe("quantile class count", () => {
    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
    });

    test("asks geostats for fewer classes than values", () => {
        const layer = {
            resId: 2,
            name: "Yield",
            geo_repr: "colored",
            classification: "quantile",
            attribute_field_name: "yield",
            nb_class: 5,
        };
        const data = [record(1, 1), record(2, 2), record(3, 3)];
        const styling = new LayerClassifier(null).classify(layer, data);
        expect(styling.values.length - 1).toBe(2);
        expect(new LayerClassifier(null).classify(layer, [record(1, 1)])).toBe(null);
    });
});
