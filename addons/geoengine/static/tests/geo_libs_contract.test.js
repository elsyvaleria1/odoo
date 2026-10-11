/** @odoo-module native */

import * as geoLibsModule from "@geoengine/lib/geo_libs";
import { geoLibs, loadGeoLibs } from "@geoengine/lib/geo_libs";
import { before, describe, expect, test, withFetch } from "@odoo/hoot";
import { globalCachedFetch } from "@web/../tests/_framework/module_set.hoot";

describe("OpenLayers contract: heatmap and cluster", () => {
    /** @type {Object} */
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    function pointSource(count) {
        const source = new ol.source.Vector();
        for (let i = 0; i < count; i++) {
            source.addFeature(
                new ol.Feature({
                    geometry: new ol.geom.Point([i * 1000, i * 1000]),
                    record: { resId: i + 1, tonnage: i + 1 },
                    featureId: i + 1,
                }),
            );
        }
        return source;
    }

    test("the libraries actually loaded", () => {
        expect(ol).not.toBe(undefined);
        expect(ol.layer.Heatmap).not.toBe(undefined);
        expect(ol.source.Cluster).not.toBe(undefined);
    });

    test("Heatmap accepts the options the renderer passes it", () => {
        const layer = new ol.layer.Heatmap({
            source: pointSource(5),
            title: "Density",
            layerId: 7,
            radius: 8,
            blur: 15,
            weight: (feature) => feature.get("record").tonnage / 5,
            opacity: 0.8,
        });

        expect(layer.getRadius()).toBe(8);
        expect(layer.getBlur()).toBe(15);
        expect(layer.getOpacity()).toBe(0.8);
    });

    test("createCluster keeps the record on a cluster of one", () => {
        const source = pointSource(1);
        let built = 0;

        const clusterSource = new ol.source.Cluster({
            source: source,
            distance: 40,
            minDistance: 20,
            createCluster: (point, features) => {
                built++;
                const cluster = new ol.Feature({
                    geometry: point,
                    features: features,
                    count: features.length,
                });
                if (features.length === 1) {
                    const [only] = features;
                    cluster.setProperties(
                        {
                            record: only.get("record"),
                            featureId: only.get("featureId"),
                        },
                        true,
                    );
                    cluster.setId(only.getId());
                }
                return cluster;
            },
        });

        clusterSource.loadFeatures(
            [-1e7, -1e7, 1e7, 1e7],
            1000,
            ol.proj.get("EPSG:3857"),
        );

        const clusters = clusterSource.getFeatures();
        expect(built).toBeGreaterThan(0);
        expect(clusters.length).toBe(1);
        expect(clusters[0].get("count")).toBe(1);
        expect(clusters[0].get("record").resId).toBe(1);
    });

    test("a cluster of several carries a count and no record", () => {
        const source = new ol.source.Vector();
        for (let i = 0; i < 4; i++) {
            source.addFeature(
                new ol.Feature({
                    geometry: new ol.geom.Point([i, i]),
                    record: { resId: i + 1 },
                }),
            );
        }
        const clusterSource = new ol.source.Cluster({
            source: source,
            distance: 40,
            createCluster: (point, features) =>
                new ol.Feature({
                    geometry: point,
                    features: features,
                    count: features.length,
                }),
        });

        clusterSource.loadFeatures(
            [-1e7, -1e7, 1e7, 1e7],
            1000,
            ol.proj.get("EPSG:3857"),
        );

        const clusters = clusterSource.getFeatures();
        expect(clusters.length).toBe(1);
        expect(clusters[0].get("count")).toBe(4);
        expect(clusters[0].get("record")).toBe(undefined);
    });

    test("ol.sphere measures on the ellipsoid, not on the projected plane", () => {
        const at48 = new ol.geom.LineString([
            ol.proj.fromLonLat([0, 48]),
            ol.proj.fromLonLat([1, 48]),
        ]);
        const projection = ol.proj.get("EPSG:3857");

        const geodesic = ol.sphere.getLength(at48, { projection });
        const planar = at48.getLength();

        expect(geodesic / 1000).toBeGreaterThan(74);
        expect(geodesic / 1000).toBeLessThan(75);
        expect(planar / geodesic).toBeGreaterThan(1.4);
    });

    test("ol.sphere area is geodesic too", () => {
        const square = new ol.geom.Polygon([
            [
                ol.proj.fromLonLat([0, 0]),
                ol.proj.fromLonLat([1, 0]),
                ol.proj.fromLonLat([1, 1]),
                ol.proj.fromLonLat([0, 1]),
                ol.proj.fromLonLat([0, 0]),
            ],
        ]);
        const area = ol.sphere.getArea(square, {
            projection: ol.proj.get("EPSG:3857"),
        });
        expect(area / 1e6).toBeGreaterThan(12000);
        expect(area / 1e6).toBeLessThan(12600);
    });

    test("minDistance is honoured rather than rejected", () => {
        const clusterSource = new ol.source.Cluster({
            source: pointSource(3),
            distance: 40,
            minDistance: 20,
        });
        expect(clusterSource.getDistance()).toBe(40);
        expect(clusterSource.getMinDistance()).toBe(20);
    });
});

describe("classifying the population vs the page (real geostats)", () => {
    const POPULATION = Array.from({ length: 100 }, (_, i) => i + 1);
    const PAGE = POPULATION.slice(0, 20);

    test("quantile breaks differ between the page and the population", () => {
        const { geostats } = geoLibs();
        const fromPage = new geostats([...PAGE]);
        fromPage.getClassQuantile(4);
        const fromPopulation = new geostats([...POPULATION]);
        fromPopulation.getClassQuantile(4);

        expect(fromPage.bounds).not.toEqual(fromPopulation.bounds);
        expect(fromPage.bounds[fromPage.bounds.length - 1]).toBe(20);
        expect(fromPopulation.bounds[fromPopulation.bounds.length - 1]).toBe(100);
    });

    test("a category absent from the page has no class at all", () => {
        const { geostats } = geoLibs();
        const pageCategories = new geostats(["a", "b"]);
        const allCategories = new geostats(["a", "b", "c"]);
        expect(pageCategories.getClassUniqueValues()).not.toInclude("c");
        expect(allCategories.getClassUniqueValues()).toInclude("c");
    });

    test("equal-interval accepts forced bounds, which is why it needs no values", () => {
        const { geostats } = geoLibs();
        const fromPage = new geostats([...PAGE]);
        fromPage.getClassEqInterval(4, 1, 100);
        const fromPopulation = new geostats([...POPULATION]);
        fromPopulation.getClassEqInterval(4);
        expect(fromPage.bounds).toEqual(fromPopulation.bounds);
    });
});

describe("the exported bindings survive a copy made at registration", () => {
    const copied = { ...geoLibsModule };

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
    });

    test("the copy is the live export", () => {
        expect(copied.ol === geoLibsModule.ol).toBe(true);
        expect(copied.chroma === geoLibsModule.chroma).toBe(true);
        expect(copied.geostats === geoLibsModule.geostats).toBe(true);
    });

    test("reads, calls and new reach the loaded libraries", () => {
        const feature = new copied.ol.Feature({ name: "x" });
        expect(feature).toBeInstanceOf(geoLibs().ol.Feature);
        expect(feature instanceof copied.ol.Feature).toBe(true);
        expect(copied.chroma("#ff0000").hex()).toBe("#ff0000");
        expect(copied.chroma.scale(["#000000", "#ffffff"])(0.5).hex()).toBe("#808080");
        const series = new copied.geostats([1, 2, 3, 4]);
        expect(series).toBeInstanceOf(geoLibs().geostats);
    });
});
