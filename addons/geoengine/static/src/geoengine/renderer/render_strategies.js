/** @odoo-module native */

import { LruCache } from "@web/core/utils/lru_cache";

import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";
import { savedValues } from "../record_values.js";
import { labelValueFor } from "./geoengine_renderer_styling.js";
import { detectGeoJSONProjection } from "./geoengine_renderer_utils.js";
import {
    createWebGLStyleWithHighlight,
    detectGeometryType,
} from "./webgl_style_converter.js";

const debugLog = makeGeoLogger("RenderStrategy");

let _webglAvailable = null;

export class RenderStrategy {
    /**
     * @param {Object} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
    }

    /**
     * @returns {string}
     */
    getName() {
        return "RenderStrategy";
    }

    /**
     * @returns {ol.layer.Layer|Object}
     */
    createLayer() {
        throw new Error("createLayer() must be implemented by subclass");
    }

    /**
     * @param {ol.source.Vector} source
     * @param {Array} data
     * @param {Object} config
     */
    addFeatures(source, data, config) {
        const geoFieldName = config.geo_field_name;
        const attributeFieldName = config.attribute_field_name;
        const colorFieldName = config.color_field_name;
        const mapProjection = this.renderer.map.getView().getProjection();

        for (const item of data) {
            const attributes = savedValues(item);
            const geometry = attributes[geoFieldName];

            if (!geometry) {
                continue;
            }

            try {
                const jsonGeometry =
                    typeof geometry === "string" ? JSON.parse(geometry) : geometry;

                const dataProjection = this._detectProjection(jsonGeometry);

                const featureProperties = {
                    geometry: this.renderer.format.readGeometry(jsonGeometry, {
                        dataProjection: dataProjection,
                        featureProjection: mapProjection,
                    }),
                    attributes: attributes,
                    record: item,
                    model: config.model,
                    geoField: geoFieldName,
                    editable: !config.readonly,
                };

                if (
                    attributeFieldName &&
                    attributes[attributeFieldName] !== undefined
                ) {
                    featureProperties[attributeFieldName] =
                        attributes[attributeFieldName];
                }

                if (colorFieldName && attributes[colorFieldName] !== undefined) {
                    featureProperties[colorFieldName] = attributes[colorFieldName];
                }

                const featureId = item.resId || item.id || attributes.id;
                if (featureId !== undefined) {
                    featureProperties.featureId = featureId;
                }

                const label = labelValueFor(item, config);
                if (label !== null) {
                    featureProperties.label = label;
                }

                const feature = new ol.Feature(featureProperties);

                if (featureId !== undefined) {
                    feature.setId(featureId);
                }

                source.addFeature(feature);
            } catch (error) {
                console.warn(
                    `[RenderStrategy] Failed to parse geometry for record ${item.resId}:`,
                    error,
                );
            }
        }
    }

    /**
     * @param {Object} jsonGeometry
     * @returns {string}
     */
    _detectProjection(jsonGeometry) {
        return detectGeoJSONProjection(jsonGeometry);
    }
}

export class WebGLStrategy extends RenderStrategy {
    getName() {
        return "WebGLStrategy";
    }

    createLayer(config, data, styling) {
        if (typeof ol.layer.WebGLVector === "undefined") {
            console.warn(
                "[WebGLStrategy] WebGLVector not available, falling back to Canvas",
            );
            return null;
        }

        const geometryType = detectGeometryType(config, data);

        const styleConfig = createWebGLStyleWithHighlight(
            config,
            styling,
            geometryType,
        );

        if (styleConfig.unsupported) {
            debugLog(
                `WebGL cannot render "${config.name}": ${styleConfig.reason}. Falling back to Canvas.`,
            );
            return null;
        }

        const source = new ol.source.Vector();
        this.addFeatures(source, data, config);

        const layer = new ol.layer.WebGLVector({
            source: source,
            title: config.name,
            layerId: config.resId,
            style: styleConfig.style,
            variables: styleConfig.variables || {},
        });

        layer.set("styleVariables", styleConfig.variables);
        layer.set("renderStrategy", "webgl");

        if (styling?.legend) {
            this.renderer.styling.initLegend({ legend: styling.legend }, config);
        }

        return layer;
    }
}

export class CanvasStrategy extends RenderStrategy {
    getName() {
        return "CanvasStrategy";
    }

    createLayer(config, data, styling) {
        const source = new ol.source.Vector();
        this.addFeatures(source, data, config);

        const layer = new ol.layer.Vector({
            source: source,
            title: config.name,
            layerId: config.resId,
            renderBuffer: 100,
        });

        this.renderer.styling.applyStyleToLayer(config, data, styling, layer);

        layer.set("renderStrategy", "canvas");

        return layer;
    }
}

const TILE_ERROR = 3;
const CELL_STYLE_CACHE_SIZE = 500;
const MVT_LAYER_KEY = "@layer";
const CELL_COLOR = "rgba(255, 104, 10, 0.85)";
const CELL_MAX_RADIUS = 15;
const STACK_MAX_RADIUS = 8;

/**
 * @param {number} count
 * @returns {string}
 */
export function cellLabel(count) {
    if (count >= 1_000_000) {
        return `${(count / 1_000_000).toFixed(1)}M`;
    }
    if (count >= 10000) {
        return `${Math.round(count / 1000)}k`;
    }
    if (count >= 1000) {
        return `${(count / 1000).toFixed(1)}k`;
    }
    return String(count);
}

/**
 * @returns {ol.format.MVT}
 */
export function createTileFormat() {
    return new ol.format.MVT({ featureClass: ol.Feature, layerName: MVT_LAYER_KEY });
}

export class TileStrategy extends RenderStrategy {
    getName() {
        return "TileStrategy";
    }

    /**
     * @param {Object} config
     * @param {{domain: Array, extent: number[]|null}} tiled
     * @param {Object|null} styling
     * @returns {ol.layer.VectorTile}
     */
    createLayer(config, tiled, styling) {
        const model = this.renderer.props.model;
        const resModel = config.model || model.root.resModel;
        const format = createTileFormat();
        const source = new ol.source.VectorTile({
            format,
            url: `geoengine-tile/${config.resId}/{z}/{x}/{y}`,
            tileLoadFunction: (tile) => {
                tile.setLoader((extent, resolution, projection) =>
                    this._loadTile(tile, {
                        config,
                        domain: tiled.domain,
                        format,
                        extent,
                        projection,
                        resModel,
                    }),
                );
            },
        });
        const layer = new ol.layer.VectorTile({
            source,
            title: config.name,
            layerId: config.resId,
            renderBuffer: 100,
            opacity: config.geo_repr === "cluster" ? (config.layer_opacity ?? 1) : 1,
        });
        this.renderer.styling.applyStyleToLayer(config, [], styling, layer);
        const featureStyle = layer.getStyle();
        const cellStyles = new LruCache(CELL_STYLE_CACHE_SIZE);
        layer.setStyle((feature, resolution) => {
            const count = feature.get("count") || 1;
            if (count > 1) {
                const fine = Boolean(feature.get("cell"));
                const label = cellLabel(count);
                const key = `${fine}|${label}`;
                let style = cellStyles.get(key);
                if (!style) {
                    style = fine
                        ? this._stackStyle(count)
                        : this._cellStyle(count, label);
                    cellStyles.set(key, style);
                }
                return style;
            }
            return config.geo_repr === "cluster"
                ? this.renderer.layers._clusterStyle(feature)
                : featureStyle(feature, resolution);
        });
        layer.set("renderStrategy", "tiles");
        layer.set("dataExtent", tiled.extent || null);
        return layer;
    }

    /**
     * @param {number} count
     * @param {string} label
     * @returns {ol.style.Style}
     */
    _cellStyle(count, label) {
        return new ol.style.Style({
            image: new ol.style.Circle({
                radius: Math.min(7 + 2 * Math.log10(count), CELL_MAX_RADIUS),
                fill: new ol.style.Fill({ color: CELL_COLOR }),
                stroke: new ol.style.Stroke({ color: "#fff", width: 1.5 }),
            }),
            text: new ol.style.Text({
                text: label,
                fill: new ol.style.Fill({ color: "#fff" }),
                font: "bold 10px sans-serif",
            }),
        });
    }

    /**
     * Records stacked on the fine grid sit a few pixels apart: a labelled
     * bubble each would smear into one blot, so they are small marks that
     * grow with their count, which their click lists.
     *
     * @param {number} count
     * @returns {ol.style.Style}
     */
    _stackStyle(count) {
        return new ol.style.Style({
            image: new ol.style.Circle({
                radius: Math.min(4 + 1.5 * Math.log10(count), STACK_MAX_RADIUS),
                fill: new ol.style.Fill({ color: CELL_COLOR }),
                stroke: new ol.style.Stroke({ color: "#fff", width: 1 }),
            }),
        });
    }

    async _loadTile(tile, { config, domain, format, extent, projection, resModel }) {
        const [z, x, y] = tile.getTileCoord();
        const model = this.renderer.props.model;
        try {
            const result = await model.orm.silent.call(
                "geoengine.vector.layer",
                "get_tile",
                [[config.resId], z, x, y, domain],
            );
            model.reportTileDensity(config.resId, z, result.too_dense);
            if (result.too_dense) {
                tile.setFeatures([]);
                return;
            }
            const bytes = Uint8Array.fromBase64(result.tile);
            const features = bytes.length
                ? format.readFeatures(bytes.buffer, {
                      extent,
                      featureProjection: projection,
                  })
                : [];
            for (const feature of features) {
                const id = feature.getId();
                const values = { ...feature.getProperties() };
                delete values[feature.getGeometryName()];
                delete values[MVT_LAYER_KEY];
                feature.setProperties(
                    {
                        record: id === undefined ? values : { id, ...values },
                        model: resModel,
                        geoField: config.geo_field_name,
                        editable: false,
                        tiled: true,
                        layerId: config.resId,
                        featureId: id,
                    },
                    true,
                );
            }
            tile.setFeatures(features);
        } catch (error) {
            debugLog(`Tile ${z}/${x}/${y} of "${config.name}" failed`, error);
            tile.setState(TILE_ERROR);
        }
    }
}

export class ViewportHeatStrategy extends RenderStrategy {
    getName() {
        return "ViewportHeatStrategy";
    }

    /**
     * @param {Object} config
     * @param {{domain: Array, extent: number[]|null}} tiled
     * @returns {ol.layer.Heatmap}
     */
    createLayer(config, tiled) {
        const source = new ol.source.Vector();
        const layer = new ol.layer.Heatmap({
            source,
            title: config.name,
            layerId: config.resId,
            radius: config.heatmap_radius || 8,
            blur: config.heatmap_blur ?? 15,
            weight: (feature) => feature.get("heat"),
            opacity: config.layer_opacity ?? 1,
        });
        layer.set("renderStrategy", "heat");
        layer.set("dataExtent", tiled.extent || null);
        const map = this.renderer.map;
        let ticket = 0;
        const load = () => {
            const mine = ++ticket;
            return this.loadCells(config, tiled.domain, source).then((loaded) => {
                if (mine !== ticket) {
                    debugLog(
                        `Dropped heat cells of "${config.name}" a later move superseded`,
                    );
                }
                return loaded && mine === ticket ? loaded() : null;
            });
        };
        const onMoveEnd = () => {
            if (!map.getAllLayers().includes(layer)) {
                map.un("moveend", onMoveEnd);
                return;
            }
            load();
        };
        map.on("moveend", onMoveEnd);
        layer.set("loadHeatCells", load);
        load();
        return layer;
    }

    /**
     * @param {Object} config
     * @param {Array} domain
     * @param {ol.source.Vector} source
     * @returns {Promise<(() => void)|null>} what applies the cells, or null
     */
    async loadCells(config, domain, source) {
        const map = this.renderer.map;
        const size = map.getSize();
        if (!size) {
            return null;
        }
        const view = map.getView();
        const zoom = view.getZoom();
        const model = this.renderer.props.model;
        let result;
        try {
            result = await model.orm.silent.call(
                "geoengine.vector.layer",
                "get_heat_cells",
                [[config.resId], view.calculateExtent(size), zoom, domain],
            );
        } catch (error) {
            debugLog(`Heat cells of "${config.name}" failed`, error);
            return null;
        }
        return () => {
            model.reportTileDensity(config.resId, Math.round(zoom), result.too_dense);
            source.clear(true);
            if (result.too_dense) {
                return;
            }
            const max = result.cells.reduce(
                (top, [, , weight]) => Math.max(top, weight),
                0,
            );
            source.addFeatures(
                result.cells.map(
                    ([x, y, weight]) =>
                        new ol.Feature({
                            geometry: new ol.geom.Point([x, y]),
                            heat: max > 0 ? Math.sqrt(weight / max) : 0,
                            heatCell: true,
                        }),
                ),
            );
        };
    }
}

export const DEFAULT_WEBGL_THRESHOLD = 1000;

/**
 * @param {Object} layerConfig
 * @param {Object} viewConfig
 * @returns {string}
 */
export function resolveRenderEngine(layerConfig, viewConfig) {
    if (layerConfig.render_engine && layerConfig.render_engine !== "inherit") {
        return layerConfig.render_engine;
    }

    return viewConfig?.render_engine || "auto";
}

/**
 * @param {string} engine
 * @param {number} featureCount
 * @param {Object} config
 * @param {Object} renderer
 * @returns {RenderStrategy}
 */
export function createRenderStrategy(engine, featureCount, config, renderer) {
    if (engine === "auto") {
        const threshold = config.webgl_threshold || DEFAULT_WEBGL_THRESHOLD;
        const editableView = Boolean(renderer.props?.archInfo?.editable);
        const needsEditing =
            editableView && !config.readonly && renderer.isGeoengineAdmin;

        debugLog(
            `Auto-selecting for ${config.name}: count=${featureCount}, threshold=${threshold}, editing=${needsEditing}`,
        );

        if (needsEditing) {
            debugLog(`→ Selected CanvasStrategy (editing required)`);
            return new CanvasStrategy(renderer);
        }

        if (featureCount > threshold) {
            debugLog(`→ Selected WebGLStrategy (large dataset)`);
            return new WebGLStrategy(renderer);
        }

        debugLog(`→ Selected CanvasStrategy (small dataset)`);
        return new CanvasStrategy(renderer);
    }

    const strategies = {
        webgl: WebGLStrategy,
        canvas: CanvasStrategy,
    };

    const StrategyClass = strategies[engine];

    if (StrategyClass) {
        debugLog(`Explicit selection: ${engine} for ${config.name}`);
        return new StrategyClass(renderer);
    }

    debugLog(`Unknown engine '${engine}', falling back to Canvas`);
    return new CanvasStrategy(renderer);
}

/**
 * @returns {boolean}
 */
export function isWebGLAvailable() {
    if (_webglAvailable !== null) {
        return _webglAvailable;
    }
    try {
        const canvas = document.createElement("canvas");
        const gl =
            window.WebGLRenderingContext &&
            (canvas.getContext("webgl") || canvas.getContext("experimental-webgl"));
        gl?.getExtension("WEBGL_lose_context")?.loseContext();
        _webglAvailable = Boolean(gl);
    } catch {
        _webglAvailable = false;
    }
    return _webglAvailable;
}
