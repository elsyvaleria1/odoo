/** @odoo-module native */

import {
    areaDomain,
    extentRing,
    GeoengineSpatialFilter,
    nearDomain,
    pointEwkt,
    polygonEwkt,
    sridOf,
} from "@geoengine/geoengine/renderer/geoengine_spatial_filter";
import { describe, expect, test } from "@odoo/hoot";
import { Domain } from "@web/core/domain";

describe("spatial filter values (production)", () => {
    test("a geometry is written in the map's projection, to its ground precision", () => {
        expect(sridOf("EPSG:3857")).toBe(3857);
        expect(sridOf("EPSG:6372")).toBe(6372);
        expect(pointEwkt([-11982247.4123, 2887610.2567], 3857)).toBe(
            "SRID=3857;POINT(-11982247.41 2887610.26)",
        );
        expect(pointEwkt([-107.651234567891, 25.1], 4326)).toBe(
            "SRID=4326;POINT(-107.6512346 25.1)",
        );
        expect(polygonEwkt([extentRing([0, 1, 2, 3])], 3857)).toBe(
            "SRID=3857;POLYGON((0 1, 2 1, 2 3, 0 3, 0 1))",
        );
    });

    test("an area and a distance become geo domains the server evaluates", () => {
        const area = new Domain(areaDomain("the_point", "SRID=3857;POINT(1 2)"));
        expect(area.toList()).toEqual([
            ["the_point", "geo_intersect", "SRID=3857;POINT(1 2)"],
        ]);
        const near = new Domain(nearDomain("the_point", "SRID=3857;POINT(1 2)", 5));
        expect(near.toList()).toEqual([
            [
                "the_point",
                "geo_dwithin",
                { geometry: "SRID=3857;POINT(1 2)", distance: 5000, unit: "m" },
            ],
        ]);
    });
});

describe("filtering by place (production)", () => {
    const filterFor = (vectors) => {
        const created = [];
        const notified = [];
        const renderer = {
            props: { model: { root: { resModel: "gps.fix" }, layers: { vectors } } },
            map: {
                getView: () => ({
                    getProjection: () => ({ getCode: () => "EPSG:3857" }),
                    calculateExtent: () => [0, 1, 2, 3],
                }),
                getSize: () => [100, 100],
            },
            notification: { add: (message) => notified.push(message) },
        };
        const filter = new GeoengineSpatialFilter(renderer);
        filter._searchModel = () => ({
            createNewFilters: (filters) => created.push(...filters),
        });
        return { filter, created, notified };
    };

    test("the view's own geometry is filtered, never another model's", () => {
        const { filter } = filterFor([
            { model: "gps.zone", geo_field_name: "area" },
            { geo_field_name: false },
            { model: "gps.fix", geo_field_name: "the_point" },
        ]);
        expect(filter.geoFieldName).toBe("the_point");
    });

    test("the visible map becomes one facet over the view's geometry", () => {
        const { filter, created } = filterFor([{ geo_field_name: "the_point" }]);
        filter.filterVisibleMap();
        expect(created).toEqual([
            {
                description: "On the visible map",
                domain: areaDomain(
                    "the_point",
                    "SRID=3857;POLYGON((0 1, 2 1, 2 3, 0 3, 0 1))",
                ),
            },
        ]);
    });

    test("a map of other models only says it has nothing to filter", () => {
        const { filter, created, notified } = filterFor([
            { model: "gps.zone", geo_field_name: "area" },
        ]);
        filter.filterVisibleMap();
        expect(created).toEqual([]);
        expect(notified.length).toBe(1);
    });
});
