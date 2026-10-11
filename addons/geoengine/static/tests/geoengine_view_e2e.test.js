/** @odoo-module native */
import { GeoengineRenderer } from "@geoengine/geoengine/geoengine_renderer";
import { loadGeoLibs } from "@geoengine/lib/geo_libs";
import { before, describe, expect, test, withFetch } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { globalCachedFetch } from "@web/../tests/_framework/module_set.hoot";
import {
    defineModels,
    fields,
    MockServer,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
    webModels,
} from "@web/../tests/web_test_helpers";

function point(x, y) {
    return JSON.stringify({
        type: "Point",
        coordinates: [x, y],
        crs: { type: "name", properties: { name: "EPSG:3857" } },
    });
}

class GeoSite extends models.Model {
    _name = "geo.site";
    name = fields.Char();
    pt = fields.Char();
    _records = [
        { id: 1, name: "a", pt: point(0, 0) },
        { id: 2, name: "b", pt: point(1000, 1000) },
        { id: 3, name: "c", pt: point(2000, 2000) },
    ];
}
defineModels({ ...webModels, GeoSite });

const ARCH = `
    <geoengine>
        <field name="name"/>
        <field name="pt"/>
        <templates><t t-name="info_box"><div><t t-out="record.name.value"/></div></t></templates>
    </geoengine>`;

function layersPayload() {
    return {
        backgrounds: [
            {
                id: 1,
                name: "OSM",
                raster_type: "osm",
                overlay: false,
                opacity: 1,
                sequence: 1,
            },
        ],
        actives: [
            {
                id: 5,
                resId: 5,
                resModel: "geoengine.vector.layer",
                name: "Sites",
                model: "geo.site",
                model_domain: "[]",
                geo_field_name: "pt",
                attribute_field_name: false,
                color_field_name: false,
                heatmap_weight_field_name: false,
                geo_repr: "basic",
                render_engine: "canvas",
                active_on_startup: true,
                sequence: 1,
                layer_opacity: 1,
                begin_color: "#3388ff",
                display_polygon_labels: false,
                readonly: false,
            },
        ],
        projection: "EPSG:3857",
        default_map_extent: false,
        restricted_extent: false,
        default_map_zoom: 5,
        render_engine: "auto",
        webgl_threshold: 1000,
        controls: {
            attribution: true,
            fullscreen: false,
            mouse_position: false,
            overview_map: false,
            zoom_slider: false,
        },
        validation: { valid: true, errors: [], warnings: [] },
    };
}

function siteFeatures(renderer) {
    const layer = renderer.vectorLayersResult.find((l) => l.get("layerId") === 5);
    return layer
        ? layer
              .getSource()
              .getFeatures()
              .map((f) => f.get("record").data.name)
              .sort()
        : null;
}

async function settle() {
    for (let i = 0; i < 10; i++) {
        await animationFrame();
    }
}

describe("geoengine view end to end", () => {
    let renderer;

    before(async () => {
        await withFetch(globalCachedFetch, () => loadGeoLibs());
    });

    async function mountMap() {
        renderer = null;
        patchWithCleanup(GeoengineRenderer.prototype, {
            setup() {
                super.setup();
                renderer = this;
            },
        });
        onRpc("get_layers", () => layersPayload());
        await mountView({ type: "geoengine", resModel: "geo.site", arch: ARCH });
        await settle();
    }

    test("the first paint draws every record of the view", async () => {
        await mountMap();
        expect(".ol-viewport").toHaveCount(1);
        expect(siteFeatures(renderer)).toEqual(["a", "b", "c"]);
        expect(renderer.props.model.layers.vectors).toHaveLength(1);
        expect(renderer.props.model.layers.rasters).toHaveLength(1);
    });

    test("a narrowing load redraws the map (it used to stay at the first paint)", async () => {
        await mountMap();
        await renderer.props.model.load({ domain: [["name", "=", "b"]] });
        await settle();
        expect(siteFeatures(renderer)).toEqual(["b"]);

        await renderer.props.model.load({ domain: [] });
        await settle();
        expect(siteFeatures(renderer)).toEqual(["a", "b", "c"]);
    });

    test("a root reload through the list (the save path) redraws too", async () => {
        await mountMap();
        MockServer.env["geo.site"].find((r) => r.id === 1).pt = point(9000, 9000);
        await renderer.props.model.root.load();
        await settle();
        const layer = renderer.vectorLayersResult.find((l) => l.get("layerId") === 5);
        const moved = layer
            .getSource()
            .getFeatures()
            .find((f) => f.get("record").data.name === "a");
        expect(moved.getGeometry().getCoordinates()).toEqual([9000, 9000]);
    });

    test("the panel toggle reaches the OpenLayers layer through the model", async () => {
        await mountMap();
        const layer = renderer.vectorLayersResult.find((l) => l.get("layerId") === 5);
        expect(layer.getVisible()).toBe(true);
        renderer.setLayerVisibility(5, false);
        expect(layer.getVisible()).toBe(false);
    });
});
