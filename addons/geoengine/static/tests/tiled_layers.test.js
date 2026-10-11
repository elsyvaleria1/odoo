/** @odoo-module native */

import { INTERVAL, proportionalRadius } from "@geoengine/geoengine/classification";
import { GeoengineModel } from "@geoengine/geoengine/geoengine_model";
import { LayerClassifier } from "@geoengine/geoengine/layer_classifier";
import { GeoengineRendererInteractions } from "@geoengine/geoengine/renderer/geoengine_renderer_interactions";
import {
    cellLabel,
    createTileFormat,
    TileStrategy,
    ViewportHeatStrategy,
} from "@geoengine/geoengine/renderer/render_strategies";
import { geoLibs, loadGeoLibs } from "@geoengine/lib/geo_libs";
import { before, describe, expect, test, withFetch } from "@odoo/hoot";
import { globalCachedFetch } from "@web/../tests/_framework/module_set.hoot";

const TILE =
    "GkwKCGZlYXR1cmVzEg8IBxICAQAYASIFCdAPsDASDRICAAEYASIFCfAukBEaBWNvdW50GgVzY29yZSIJGQAAAAAAAAxAIgIoDCiAIHgC";

const EXTENT = [-1000, -1000, 1000, 1000];

describe("when a layer is tiled (production)", () => {
    const tiledLayer = ({
        config = { resId: 5, name: "fixes", model: "gps.fix", geo_repr: "basic" },
        root = {},
        projection = "EPSG:3857",
        count = 0,
        layerDomain = [],
    } = {}) => {
        const calls = [];
        const model = {
            getMapConfig: () => ({ projection }),
            evalDomain: () => layerDomain,
            _effectiveLayerDomain: GeoengineModel.prototype._effectiveLayerDomain,
            orm: {
                searchCount: async (...args) => {
                    calls.push(["searchCount", ...args]);
                    return count;
                },
                silent: {
                    call: async (...args) => {
                        calls.push(["call", ...args]);
                        return EXTENT;
                    },
                },
            },
        };
        const fullRoot = {
            resModel: "gps.fix",
            domain: [["speed", ">", 3]],
            records: [{ resId: 1 }],
            count: 1,
            ...root,
        };
        return GeoengineModel.prototype._tiledLayer
            .call(model, config, fullRoot)
            .then((tiled) => ({ tiled, calls }));
    };

    test("the view's own layer is tiled when the page holds less than the search matched", async () => {
        const { tiled, calls } = await tiledLayer({ root: { count: 7_000_000 } });
        expect(tiled).toEqual({ domain: [["speed", ">", 3]], extent: EXTENT });
        expect(calls).toEqual([
            [
                "call",
                "geoengine.vector.layer",
                "get_tile_extent",
                [[5], [["speed", ">", 3]]],
            ],
        ]);
    });

    test("a complete page is drawn as features", async () => {
        const { tiled, calls } = await tiledLayer();
        expect(tiled).toBe(null);
        expect(calls).toEqual([]);
    });

    test("another model's layer is tiled only beyond the fetch limit", async () => {
        const config = {
            resId: 6,
            name: "zones",
            model: "gps.zone",
            geo_repr: "basic",
        };
        const over = await tiledLayer({ config, count: 10_001 });
        expect(over.tiled.domain).toEqual([]);
        expect(over.calls[0]).toEqual([
            "searchCount",
            "gps.zone",
            [],
            { limit: 10_001 },
        ]);
        const under = await tiledLayer({ config, count: 10_000 });
        expect(under.tiled).toBe(null);
    });

    test("another projection or a grouped view keep the features path", async () => {
        const truncated = { count: 7_000_000 };
        expect(
            (await tiledLayer({ root: truncated, projection: "EPSG:4326" })).tiled,
        ).toBe(null);
        expect(
            (await tiledLayer({ root: { ...truncated, isGrouped: true } })).tiled,
        ).toBe(null);
    });

    test("a heatmap too large to send reads its view instead", async () => {
        const { tiled } = await tiledLayer({
            root: { count: 7_000_000 },
            config: { resId: 5, name: "heat", model: "gps.fix", geo_repr: "heatmap" },
        });
        expect(tiled.domain).toEqual([["speed", ">", 3]]);
    });

    test("the map draws every match only when the view's own layer is tiled", () => {
        const drawsEveryMatch = (vectorLayers) =>
            GeoengineModel.prototype.drawsEveryMatch.call({
                root: { resModel: "gps.fix", data: { vectorLayers } },
            });
        expect(drawsEveryMatch([{ config: {}, tiled: { domain: [] } }])).toBe(true);
        expect(
            drawsEveryMatch([{ config: { model: "gps.zone" }, tiled: { domain: [] } }]),
        ).toBe(false);
        expect(drawsEveryMatch([{ config: {}, tiled: null }])).toBe(false);
    });
});

describe("tile loading (production)", () => {
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    const loadTile = async (answer) => {
        const calls = [];
        const dense = [];
        const renderer = {
            props: {
                model: {
                    root: { resModel: "gps.fix" },
                    reportTileDensity: (layerId, zoom, tooDense) =>
                        dense.push([layerId, zoom, tooDense]),
                    orm: {
                        silent: {
                            call: async (...args) => {
                                calls.push(args);
                                return answer();
                            },
                        },
                    },
                },
            },
        };
        const tile = {
            features: null,
            state: null,
            getTileCoord: () => [3, 1, 2],
            setFeatures(features) {
                this.features = features;
            },
            setState(state) {
                this.state = state;
            },
        };
        await new TileStrategy(renderer)._loadTile(tile, {
            config: { resId: 5, name: "fixes", geo_field_name: "the_point" },
            domain: [["speed", ">", 3]],
            format: createTileFormat(),
            extent: [0, 0, 4096, 4096],
            projection: ol.proj.get("EPSG:3857"),
            resModel: "gps.fix",
        });
        return { tile, calls, dense };
    };

    test("a tile asks for its own coordinates and the layer's domain", async () => {
        const { calls } = await loadTile(() => ({ tile: TILE, too_dense: false }));
        expect(calls).toEqual([
            ["geoengine.vector.layer", "get_tile", [[5], 3, 1, 2, [["speed", ">", 3]]]],
        ]);
    });

    test("a record arrives as the plain record the styles read, a cell with its count", async () => {
        const { tile } = await loadTile(() => ({ tile: TILE, too_dense: false }));
        const [record, cell] = tile.features;
        expect(record.getId()).toBe(7);
        expect(record.get("record")).toEqual({ id: 7, score: 3.5 });
        expect(record.get("tiled")).toBe(true);
        expect(record.get("editable")).toBe(false);
        expect(record.get("model")).toBe("gps.fix");
        expect(record.get("geoField")).toBe("the_point");
        expect(cell.getId()).toBe(undefined);
        expect(cell.get("count")).toBe(12);
        expect(cell.get("record")).toEqual({ count: 12 });
    });

    test("a tile over its budget draws nothing and reports the layer", async () => {
        const { tile, dense } = await loadTile(() => ({ tile: "", too_dense: true }));
        expect(tile.features).toEqual([]);
        expect(dense).toEqual([[5, 3, true]]);
    });

    test("a failed tile is marked failed rather than drawn empty", async () => {
        const { tile } = await loadTile(() => {
            throw new Error("access denied");
        });
        expect(tile.features).toBe(null);
        expect(tile.state).toBe(3);
    });
});

describe("tiled styling (production)", () => {
    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
    });

    test("cell counts are short enough for their bubble", () => {
        expect([2, 999, 1234, 12_345, 7_637_647].map(cellLabel)).toEqual([
            "2",
            "999",
            "1.2k",
            "12k",
            "7.6M",
        ]);
    });

    test("a proportional symbol is sized by its place in the population's range", () => {
        const styling = { minValue: 10, maxValue: 30, minSize: 4, maxSize: 20 };
        expect(proportionalRadius(styling, 10)).toBe(4);
        expect(proportionalRadius(styling, 20)).toBe(12);
        expect(proportionalRadius(styling, 30)).toBe(20);
        expect(proportionalRadius(styling, 99)).toBe(20);
        expect(proportionalRadius(styling, false)).toBe(4);
        expect(proportionalRadius({ ...styling, maxValue: 10 }, 10)).toBe(12);
    });

    test("interval classes of a tiled layer split the population's bounds", () => {
        const styling = new LayerClassifier({}).classify(
            {
                resId: 9,
                name: "speed",
                geo_repr: "colored",
                classification: INTERVAL,
                attribute_field_name: "speed",
                nb_class: 4,
            },
            [],
            { bounds: { min: 0, max: 100 } },
        );
        expect(styling.values).toEqual([0, 25, 50, 75, 100]);
        expect(styling.colors.length).toBe(4);
    });
});

describe("a dense tile's warning (production)", () => {
    const fakeModel = (status = null) => {
        const statuses = new Map(status ? [[5, status]] : []);
        return {
            _denseZooms: new Map(),
            getLayerStatus: (id) => statuses.get(id) || null,
            setLayerStatus: (id, value) => statuses.set(id, value),
            report(zoom, dense) {
                GeoengineModel.prototype.reportTileDensity.call(this, 5, zoom, dense);
                return statuses.get(5)?.warning ?? null;
            },
        };
    };

    test("it stays while the zoom shown holds a refused tile, and clears at another", () => {
        const model = fakeModel();
        expect(model.report(6, true)).toMatch(/too many records/);
        expect(model.report(6, false)).toMatch(/too many records/);
        expect(model.report(8, false)).toBe(null);
        expect(model.report(6, false)).toMatch(/too many records/);
    });

    test("another warning of the layer is not replaced", () => {
        const model = fakeModel({
            loading: false,
            error: null,
            warning: "Classification failed",
        });
        expect(model.report(6, true)).toBe("Classification failed");
        expect(model.report(8, false)).toBe("Classification failed");
    });
});

describe("a tiled layer's population (production)", () => {
    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
    });

    const loadPopulation = async (classification, answers) => {
        const calls = [];
        const orm = {
            call: async (model, method, args, kwargs) => {
                calls.push([method, kwargs]);
                return answers[method];
            },
        };
        const population = await new LayerClassifier(orm).loadPopulation(
            {
                resId: 9,
                name: "speed",
                geo_repr: "colored",
                classification,
                attribute_field_name: "speed",
                nb_class: 4,
            },
            [["speed", ">", 0]],
        );
        return { population, calls };
    };

    test("unique classes read each value once", async () => {
        const { population, calls } = await loadPopulation("unique", {
            get_class_values: ["slow", "fast"],
        });
        expect(population).toEqual({ values: ["slow", "fast"] });
        expect(calls).toEqual([["get_class_values", { distinct: true }]]);
    });

    test("quantiles of a population too large to send are cut by the database", async () => {
        const { population, calls } = await loadPopulation("quantile", {
            get_class_values: [],
            get_class_quantiles: [0, 10, 40, 60, 90],
        });
        expect(population).toEqual({ quantiles: [0, 10, 40, 60, 90] });
        expect(calls).toEqual([
            ["get_class_values", {}],
            ["get_class_quantiles", { nb_class: 4 }],
        ]);
    });

    test("a tiled layer's quantile classes are the database's bounds", () => {
        const styling = new LayerClassifier({}).classify(
            {
                resId: 9,
                name: "speed",
                geo_repr: "colored",
                classification: "quantile",
                attribute_field_name: "speed",
                nb_class: 4,
            },
            [],
            { quantiles: [0, 10, 40, 60, 90] },
        );
        expect(styling.values).toEqual([0, 10, 40, 60, 90]);
        expect(styling.colors.length).toBe(4);
    });
});

describe("clicking a tile cell (production)", () => {
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    const clickCell = async (properties) => {
        const calls = [];
        const view = {
            getZoom: () => 12,
            animate: (options) => calls.push(["animate", options]),
        };
        const renderer = {
            state: {},
            overlay: { setPosition: (coord) => calls.push(["position", coord]) },
            map: { getView: () => view },
            popupRef: { el: null },
            props: {
                model: {
                    readCellRecords: async (layerId, cell) => {
                        calls.push(["readCellRecords", layerId, cell]);
                        return {
                            records: [{ id: 3, display_name: "fix 3" }],
                            more: true,
                        };
                    },
                },
            },
        };
        const feature = new ol.Feature({
            geometry: new ol.geom.Point([0, 0]),
            tiled: true,
            layerId: 5,
            model: "gps.fix",
            ...properties,
        });
        await new GeoengineRendererInteractions(renderer)._showTiledFeature(
            feature,
            [10, 20],
        );
        return { calls, state: renderer.state };
    };

    test("a cell of stacked records lists them where it was clicked", async () => {
        const { calls, state } = await clickCell({ count: 40, cell: "16/1/2" });
        expect(calls).toEqual([
            ["readCellRecords", 5, "16/1/2"],
            ["position", undefined],
            ["position", [10, 20]],
        ]);
        expect(state.popupList).toEqual({
            key: 1,
            count: 40,
            more: true,
            records: [{ id: 3, display_name: "fix 3" }],
            resModel: "gps.fix",
            coord: [10, 20],
        });
    });

    test("a coarse cell zooms in instead", async () => {
        const { calls, state } = await clickCell({ count: 40 });
        expect(calls.at(-1)).toEqual([
            "animate",
            { center: [10, 20], zoom: 14, duration: 250 },
        ]);
        expect(state.popupList).toBe(null);
    });

    test("a cell of a layer that is not tiled lists nothing", async () => {
        const result = await GeoengineModel.prototype.readCellRecords.call(
            {
                root: {
                    data: { vectorLayers: [{ config: { resId: 5 }, tiled: null }] },
                },
            },
            5,
            "16/1/2",
        );
        expect(result).toEqual({ records: [], more: false });
    });
});

describe("a heatmap read by view (production)", () => {
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    const heatRenderer = (answer) => {
        const calls = [];
        const dense = [];
        const listeners = [];
        const map = {
            getSize: () => [100, 100],
            getView: () => ({
                getZoom: () => 9.4,
                calculateExtent: () => [0, 0, 10, 10],
            }),
            on: (type, listener) => listeners.push(listener),
            un: () => {},
            getAllLayers: () => [],
        };
        const renderer = {
            map,
            props: {
                model: {
                    reportTileDensity: (...args) => dense.push(args),
                    orm: {
                        silent: {
                            call: (...args) => {
                                calls.push(args);
                                return answer(calls.length);
                            },
                        },
                    },
                },
            },
        };
        return { renderer, calls, dense, listeners };
    };
    const config = { resId: 7, name: "heat", geo_repr: "heatmap" };

    test("a view's cells become points weighted by their share of the densest", async () => {
        const { renderer, calls } = heatRenderer(async () => ({
            cells: [
                [1, 2, 1],
                [3, 4, 99],
            ],
            too_dense: false,
        }));
        const source = new ol.source.Vector();
        const apply = await new ViewportHeatStrategy(renderer).loadCells(
            config,
            [["speed", ">", 3]],
            source,
        );
        apply();
        expect(calls).toEqual([
            [
                "geoengine.vector.layer",
                "get_heat_cells",
                [[7], [0, 0, 10, 10], 9.4, [["speed", ">", 3]]],
            ],
        ]);
        const heat = source
            .getFeatures()
            .map((f) => [
                f.getGeometry().getCoordinates(),
                Number(f.get("heat").toFixed(3)),
            ])
            .sort((a, b) => a[1] - b[1]);
        expect(heat).toEqual([
            [[1, 2], Number(Math.sqrt(1 / 99).toFixed(3))],
            [[3, 4], 1],
        ]);
    });

    test("a view over its budget empties the heatmap and reports the layer", async () => {
        const { renderer, dense } = heatRenderer(async () => ({
            cells: [],
            too_dense: true,
        }));
        const source = new ol.source.Vector();
        source.addFeature(new ol.Feature({ geometry: new ol.geom.Point([0, 0]) }));
        (await new ViewportHeatStrategy(renderer).loadCells(config, [], source))();
        expect(source.getFeatures()).toEqual([]);
        expect(dense).toEqual([[7, 9, true]]);
    });

    test("cells a later move superseded are not drawn", async () => {
        const answers = [];
        const { renderer } = heatRenderer(
            (n) =>
                new Promise((resolve) => {
                    answers[n - 1] = resolve;
                }),
        );
        const layer = new ViewportHeatStrategy(renderer).createLayer(config, {
            domain: [],
            extent: null,
        });
        const second = layer.get("loadHeatCells")();
        answers[1]({ cells: [[5, 5, 1]], too_dense: false });
        await second;
        answers[0]({
            cells: [
                [9, 9, 1],
                [8, 8, 1],
            ],
            too_dense: false,
        });
        for (let tick = 0; tick < 10; tick++) {
            await Promise.resolve();
        }
        const coords = layer
            .getSource()
            .getFeatures()
            .map((f) => f.getGeometry().getCoordinates());
        expect(coords).toEqual([[5, 5]]);
    });
});
