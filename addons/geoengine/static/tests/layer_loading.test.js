/** @odoo-module native */

import { GeoengineModel } from "@geoengine/geoengine/geoengine_model";
import { RasterLayerBuilder } from "@geoengine/geoengine/renderer/raster_layers";
import { CanvasStrategy } from "@geoengine/geoengine/renderer/render_strategies";
import { geoLibs, loadGeoLibs } from "@geoengine/lib/geo_libs";
import { before, describe, expect, test, withFetch } from "@odoo/hoot";
import { globalCachedFetch } from "@web/../tests/_framework/module_set.hoot";
import { user } from "@web/core/user";

describe("layer domain evaluation (production)", () => {
    const evalDomain = (model_domain, records = []) =>
        GeoengineModel.prototype.evalDomain.call(
            { root: { records } },
            { model_domain },
        );

    test("a domain naming uid reads the current user", () => {
        expect(evalDomain("[('user_id', '=', uid)]")).toEqual([
            ["user_id", "=", user.userId],
        ]);
    });

    test("{ACTIVE_IDS} becomes the ids of the drawn records", () => {
        expect(
            evalDomain("[('id', 'in', '{ACTIVE_IDS}')]", [{ resId: 3 }, { resId: 5 }]),
        ).toEqual([["id", "in", [3, 5]]]);
    });

    test("a domain that cannot be evaluated fails the layer instead of unfiltering it", () => {
        expect(() => evalDomain("[('id', '=', no_such_name)]")).toThrow(
            /cannot be evaluated/,
        );
    });
});

describe("layer data errors (production)", () => {
    test("a failing fetch rejects, so the layer reports its error", async () => {
        const model = {
            root: { resModel: "res.partner", records: [], domain: [] },
            inflightFetches: new Map(),
            evalDomain: () => [],
            _effectiveLayerDomain: (_config, domain) => domain,
            _doFetchLayerData: () => Promise.reject(new Error("access denied")),
        };
        await expect(
            GeoengineModel.prototype.getLayerData.call(
                model,
                { model: "res.country", name: "countries", resId: 1 },
                ["id"],
            ),
        ).rejects.toThrow("access denied");
    });
});

describe("map objects built from the layer payload", () => {
    let ol;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
        ({ ol } = geoLibs());
    });

    test("every raster layer carries the id the base-map switch matches on", () => {
        const builder = new RasterLayerBuilder({});
        const layers = builder.createBackgroundLayers([
            { id: 1, name: "osm", raster_type: "osm" },
            {
                id: 2,
                name: "tiles",
                raster_type: "xyz",
                url: "https://t/{z}/{x}/{y}.png",
            },
            { id: 3, name: "wmts", raster_type: "wmts", url: "https://w" },
        ]);
        expect(layers.map((layer) => layer.get("layerId"))).toEqual([1, 2, 3]);
    });

    test("a feature knows the field it is drawn from and whether it may be edited", () => {
        const renderer = {
            map: new ol.Map({ view: new ol.View() }),
            format: new ol.format.GeoJSON(),
        };
        const source = new ol.source.Vector();
        const geometry = JSON.stringify({ type: "Point", coordinates: [1, 2] });
        const record = { resId: 7, _values: { id: 7, visited: geometry } };
        new CanvasStrategy(renderer).addFeatures(source, [record], {
            geo_field_name: "visited",
            model: "gps.device",
            readonly: true,
        });
        const [feature] = source.getFeatures();
        expect(feature.get("geoField")).toBe("visited");
        expect(feature.get("editable")).toBe(false);
    });
});

describe("concurrent loads (production)", () => {
    test("a slower, older load does not overwrite a newer one", async () => {
        const root = { data: null };
        const pending = [];
        const model = {
            root,
            layers: { vectors: [] },
            _geoDataTicket: 0,
            _prepareVectorLayers: () => new Promise((resolve) => pending.push(resolve)),
            _prepareRasterLayers: () => [],
        };
        const prepare = GeoengineModel.prototype._prepareGeoData;
        const older = prepare.call(model, root);
        const newer = prepare.call(model, root);
        pending[1](["page 2"]);
        await newer;
        pending[0](["page 1"]);
        await older;
        expect(root.data.vectorLayers).toEqual(["page 2"]);
    });
});

describe("layers drawn on demand (production)", () => {
    test("a hidden layer is read when it is first shown, and only then", async () => {
        const prepared = [];
        const model = {
            root: {},
            deferredLayers: new Set([7]),
            _prepareGeoData: async (root) => prepared.push(root),
        };
        await GeoengineModel.prototype.showLayer.call(model, 8);
        expect(prepared.length).toBe(0);
        await GeoengineModel.prototype.showLayer.call(model, 7);
        expect(prepared.length).toBe(1);
    });

    test("a session filter survives a reload of the layer configuration", async () => {
        const model = {
            root: {},
            layers: { vectors: [{ resId: 3, isVisible: true, model_domain: "[]" }] },
            layerDomainOverrides: new Map(),
            config: { resModel: "res.partner" },
            _prepareGeoData: async () => {},
            _loadLayerConfigurations: async function () {
                this.layers.vectors = [
                    { resId: 3, isVisible: false, model_domain: "[]" },
                ];
            },
        };
        await GeoengineModel.prototype.overrideLayerDomain.call(
            model,
            3,
            "[('name', '=', 'a')]",
        );
        await GeoengineModel.prototype.reloadLayerConfigurations.call(model);
        expect(model.layers.vectors[0].model_domain).toBe("[('name', '=', 'a')]");
        expect(model.layers.vectors[0].isVisible).toBe(true);
    });
});

describe("server-evaluated layer domains (production)", () => {
    const evalDomain = (layerConfig, records = [], overrides = new Map()) =>
        GeoengineModel.prototype.evalDomain.call(
            { root: { records }, layerDomainOverrides: overrides },
            layerConfig,
        );

    test("the drawn ids replace every placeholder, nested ones included", () => {
        const domain = [
            ["create_uid", "=", 7],
            [
                "zone",
                "geo_intersect",
                { "res.zone.area": [["id", "in", "{ACTIVE_IDS}"]] },
            ],
        ];
        expect(evalDomain({ resId: 1, domain }, [{ resId: 3 }])).toEqual([
            ["create_uid", "=", 7],
            ["zone", "geo_intersect", { "res.zone.area": [["id", "in", [3]]] }],
        ]);
    });

    test("a domain the server could not evaluate fails the layer", () => {
        expect(() =>
            evalDomain({ resId: 1, domain: null, model_domain: "[x]" }),
        ).toThrow(/cannot be evaluated/);
    });

    test("a session filter is evaluated from its text", () => {
        const overrides = new Map([[1, "[('name', '=', 'a')]"]]);
        expect(
            evalDomain(
                { resId: 1, domain: [], model_domain: "[('name', '=', 'a')]" },
                [],
                overrides,
            ),
        ).toEqual([["name", "=", "a"]]);
    });
});
