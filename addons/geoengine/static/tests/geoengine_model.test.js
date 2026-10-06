import {
    needsPopulationBounds,
    needsPopulationValues,
} from "@geoengine/geoengine/classification";
import {
    DomainHasher,
    GeoengineModel,
    layerTruncationWarning,
} from "@geoengine/geoengine/geoengine_model";
import { describe, expect, test } from "@odoo/hoot";

describe("DomainHasher (production)", () => {
    test("returns '[]' for empty / null / undefined", () => {
        expect(DomainHasher.hash([])).toBe("[]");
        expect(DomainHasher.hash(null)).toBe("[]");
        expect(DomainHasher.hash(undefined)).toBe("[]");
    });

    test("produces a non-empty string mentioning the field", () => {
        const hash = DomainHasher.hash([["country_id", "=", 1]]);
        expect(typeof hash).toBe("string");
        expect(hash.length).toBeGreaterThan(0);
        expect(hash).toInclude("country_id");
    });

    test("is deterministic for the same domain", () => {
        const domain = [["field", "=", "value"]];
        expect(DomainHasher.hash(domain)).toBe(DomainHasher.hash(domain));
    });

    test("distinguishes domains that differ by value", () => {
        expect(DomainHasher.hash([["f", "=", "a"]])).not.toBe(
            DomainHasher.hash([["f", "=", "b"]]),
        );
    });

    test("distinguishes domains that differ by operator structure", () => {
        const or = DomainHasher.hash(["|", ["a", "=", 1], ["b", "=", 2]]);
        const and = DomainHasher.hash(["&", ["a", "=", 1], ["b", "=", 2]]);
        expect(or).not.toBe(and);
    });
});

describe("layer field availability (production)", () => {
    const asModel = (records) => ({
        root: { records },
        _getLayerFields: GeoengineModel.prototype._getLayerFields,
        _missingLayerFields: GeoengineModel.prototype._missingLayerFields,
    });
    const layer = {
        geo_field_name: "the_geom",
        attribute_field_name: "sales_band",
        color_field_name: "display_color",
    };

    test("reports the styled fields the view's records do not carry", () => {
        const model = asModel([{ _values: { id: 1, the_geom: "{}", name: "a" } }]);
        expect(model._missingLayerFields(layer)).toEqual([
            "sales_band",
            "display_color",
        ]);
    });

    test("reports nothing when every styled field is present", () => {
        const model = asModel([
            {
                _values: {
                    id: 1,
                    the_geom: "{}",
                    sales_band: "busy",
                    display_color: "#fff",
                },
            },
        ]);
        expect(model._missingLayerFields(layer)).toEqual([]);
    });

    test("a field present but empty still counts as carried", () => {
        const model = asModel([
            {
                _values: {
                    id: 1,
                    the_geom: "{}",
                    sales_band: false,
                    display_color: false,
                },
            },
        ]);
        expect(model._missingLayerFields(layer)).toEqual([]);
    });

    test("reports nothing when there are no records to inspect", () => {
        expect(asModel([])._missingLayerFields(layer)).toEqual([]);
    });
});

describe("layerTruncationWarning (production)", () => {
    test("says nothing when the fetch came back under the cap", () => {
        expect(layerTruncationWarning(0)).toBe(null);
        expect(layerTruncationWarning(1)).toBe(null);
        expect(layerTruncationWarning(9999)).toBe(null);
    });

    test("warns at the cap, which is where 'there may be more' starts", () => {
        expect(layerTruncationWarning(10000)).not.toBe(null);
    });

    test("still warns above the cap", () => {
        expect(layerTruncationWarning(10001)).not.toBe(null);
    });

    test("names the limit, so the message says what to do about it", () => {
        expect(layerTruncationWarning(10000)).toInclude("10000");
    });
});

describe("needsPopulationBounds (production)", () => {
    test("equal-interval choropleths need it", () => {
        expect(
            needsPopulationBounds({
                geo_repr: "colored",
                classification: "interval",
                attribute_field_name: "total_sales",
            }),
        ).toBe(true);
    });

    test("proportional symbols need it", () => {
        expect(
            needsPopulationBounds({
                geo_repr: "proportion",
                attribute_field_name: "total_sales",
            }),
        ).toBe(true);
    });

    test("quantile does not: breaks are order statistics, not aggregates", () => {
        expect(
            needsPopulationBounds({
                geo_repr: "colored",
                classification: "quantile",
                attribute_field_name: "total_sales",
            }),
        ).toBe(false);
    });

    test("unique does not: the classes are categories", () => {
        expect(
            needsPopulationBounds({
                geo_repr: "colored",
                classification: "unique",
                attribute_field_name: "sales_band",
            }),
        ).toBe(false);
    });

    test("colored_field does not: the colour is stored per record", () => {
        expect(
            needsPopulationBounds({
                geo_repr: "colored_field",
                attribute_field_name: "display_color",
            }),
        ).toBe(false);
    });

    test("nothing to measure without an attribute field", () => {
        expect(needsPopulationBounds({ geo_repr: "proportion" })).toBe(false);
        expect(needsPopulationBounds(null)).toBe(false);
    });
});

describe("needsPopulationValues (production)", () => {
    test("quantile needs the values", () => {
        expect(
            needsPopulationValues({
                geo_repr: "colored",
                classification: "quantile",
                attribute_field_name: "total_sales",
            }),
        ).toBe(true);
    });

    test("unique needs the values: a category only on page 2 has no colour otherwise", () => {
        expect(
            needsPopulationValues({
                geo_repr: "colored",
                classification: "unique",
                attribute_field_name: "sales_band",
            }),
        ).toBe(true);
    });

    test("interval does not: min and max are enough, and cheaper", () => {
        expect(
            needsPopulationValues({
                geo_repr: "colored",
                classification: "interval",
                attribute_field_name: "total_sales",
            }),
        ).toBe(false);
    });

    test("proportion does not: it is scaled by min/max, not classified", () => {
        expect(
            needsPopulationValues({
                geo_repr: "proportion",
                attribute_field_name: "total_sales",
            }),
        ).toBe(false);
    });

    test("the two predicates never both fire for one layer", () => {
        for (const classification of ["interval", "quantile", "unique"]) {
            for (const geo_repr of ["colored", "proportion", "colored_field"]) {
                const config = {
                    geo_repr,
                    classification,
                    attribute_field_name: "f",
                };
                expect(
                    needsPopulationBounds(config) && needsPopulationValues(config),
                ).toBe(false);
            }
        }
    });
});
