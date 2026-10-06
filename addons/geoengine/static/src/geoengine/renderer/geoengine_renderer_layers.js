/** @odoo-module native */
import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";
import { DEFAULT_COLOR, withOpacity } from "../classification.js";
import { savedValue } from "../record_values.js";
import {
    CanvasStrategy,
    createRenderStrategy,
    isWebGLAvailable,
    resolveRenderEngine,
    TileStrategy,
    ViewportHeatStrategy,
} from "./render_strategies.js";

const debugLog = makeGeoLogger("RendererLayers");

const CLUSTER_SINGLE_COLOR = withOpacity(DEFAULT_COLOR, 0.9);
const CLUSTER_GROUP_COLOR = "rgba(255, 104, 10, 0.85)";

/**
 * @param {Array} data
 * @param {string|false} weightField
 * @returns {(feature: ol.Feature) => number}
 */
export function makeHeatmapWeight(data, weightField) {
    if (!weightField) {
        return () => 1;
    }

    let maxValue = 0;
    for (const item of data) {
        const value = Number(savedValue(item, weightField));
        if (Number.isFinite(value) && value > maxValue) {
            maxValue = value;
        }
    }

    if (maxValue <= 0) {
        return () => 1;
    }

    return (feature) => {
        const value = Number(savedValue(feature.get("record"), weightField));
        if (!Number.isFinite(value) || value <= 0) {
            return 0;
        }
        return Math.min(value / maxValue, 1);
    };
}

export class GeoengineRendererLayers {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
        this._webglAvailable = isWebGLAvailable();
    }
    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @returns {ol.source.Vector}
     */
    _buildFeatureSource(layerConfig, data) {
        const source = new ol.source.Vector();
        new CanvasStrategy(this.renderer).addFeatures(source, data, layerConfig);
        return source;
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @returns {ol.layer.Heatmap}
     */
    _createHeatmapLayer(layerConfig, data) {
        const source = this._buildFeatureSource(layerConfig, data);
        const weightField = layerConfig.heatmap_weight_field_name;
        const weight = makeHeatmapWeight(data, weightField);

        const layer = new ol.layer.Heatmap({
            source: source,
            title: layerConfig.name,
            layerId: layerConfig.resId,
            radius: layerConfig.heatmap_radius || 8,
            blur: layerConfig.heatmap_blur ?? 15,
            weight: weight,
            opacity: layerConfig.layer_opacity ?? 1,
        });
        layer.set("renderStrategy", "heatmap");
        layer.setZIndex(layerConfig.sequence);
        debugLog(
            `Created heatmap "${layerConfig.name}" (${data.length} points, ` +
                `weight=${weightField || "uniform"})`,
        );
        return layer;
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @returns {ol.layer.Vector}
     */
    _createClusterLayer(layerConfig, data) {
        const source = this._buildFeatureSource(layerConfig, data);

        const clusterSource = new ol.source.Cluster({
            source: source,
            distance: layerConfig.cluster_distance || 40,
            minDistance: layerConfig.cluster_min_distance || 0,
            createCluster: (point, features) => {
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
                            model: only.get("model"),
                            attributes: only.get("attributes"),
                            featureId: only.get("featureId"),
                        },
                        true,
                    );
                    cluster.setId(only.getId());
                }
                return cluster;
            },
        });

        const layer = new ol.layer.Vector({
            source: clusterSource,
            title: layerConfig.name,
            layerId: layerConfig.resId,
            opacity: layerConfig.layer_opacity ?? 1,
            style: (feature) => this._clusterStyle(feature),
        });
        layer.set("renderStrategy", "cluster");
        layer.setZIndex(layerConfig.sequence);
        debugLog(
            `Created cluster layer "${layerConfig.name}" (${data.length} points, ` +
                `distance=${layerConfig.cluster_distance || 40}px)`,
        );
        return layer;
    }

    /**
     * @param {ol.Feature} feature
     * @returns {ol.style.Style}
     */
    _clusterStyle(feature) {
        const count = feature.get("count") || 1;
        const radius = count === 1 ? 6 : Math.min(10 + Math.sqrt(count) * 2, 28);

        const style = new ol.style.Style({
            image: new ol.style.Circle({
                radius: radius,
                fill: new ol.style.Fill({
                    color: count === 1 ? CLUSTER_SINGLE_COLOR : CLUSTER_GROUP_COLOR,
                }),
                stroke: new ol.style.Stroke({ color: "#fff", width: 2 }),
            }),
        });
        if (count > 1) {
            style.setText(
                new ol.style.Text({
                    text: String(count),
                    fill: new ol.style.Fill({ color: "#fff" }),
                    font: "bold 11px Calibri,sans-serif",
                }),
            );
        }
        return style;
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @param {Object} styling
     * @returns {ol.layer.Vector|ol.layer.WebGLVector}
     */
    createVectorLayer(layerConfig, data, styling, tiled = null) {
        if (tiled) {
            const Strategy =
                layerConfig.geo_repr === "heatmap"
                    ? ViewportHeatStrategy
                    : TileStrategy;
            const layer = new Strategy(this.renderer).createLayer(
                layerConfig,
                tiled,
                styling,
            );
            layer.setZIndex(layerConfig.sequence);
            return layer;
        }
        const featureCount = data?.length || 0;

        debugLog("createVectorLayer() - Creating layer:", {
            name: layerConfig.name,
            model: layerConfig.model,
            dataCount: featureCount,
            renderEngine: layerConfig.render_engine,
        });

        if (!data || data.length === 0) {
            debugLog("No data for layer:", layerConfig.name);
            const emptyLayer = new ol.layer.Vector({
                title: layerConfig.name,
                source: new ol.source.Vector(),
                layerId: layerConfig.resId,
            });
            emptyLayer.setZIndex(layerConfig.sequence);
            return emptyLayer;
        }

        if (layerConfig.geo_repr === "heatmap") {
            return this._createHeatmapLayer(layerConfig, data);
        }
        if (layerConfig.geo_repr === "cluster") {
            return this._createClusterLayer(layerConfig, data);
        }

        const viewConfig = this.renderer.props.model.getRenderEngineConfig();
        const resolvedEngine = resolveRenderEngine(layerConfig, viewConfig);

        const configWithThreshold = {
            ...layerConfig,
            webgl_threshold: layerConfig.webgl_threshold || viewConfig.webgl_threshold,
        };

        let effectiveEngine = resolvedEngine;
        if (resolvedEngine === "webgl" && !this._webglAvailable) {
            debugLog("WebGL not available, falling back to Canvas");
            effectiveEngine = "canvas";
        }

        const strategy = createRenderStrategy(
            effectiveEngine,
            featureCount,
            configWithThreshold,
            this.renderer,
        );

        debugLog(
            `Using ${strategy.getName()} for ${layerConfig.name} (${featureCount} features)`,
        );

        let layerResult = strategy.createLayer(configWithThreshold, data, styling);

        if (!layerResult) {
            debugLog("Strategy declined the layer, falling back to Canvas");
            layerResult = new CanvasStrategy(this.renderer).createLayer(
                configWithThreshold,
                data,
                styling,
            );
        }

        layerResult.setZIndex(layerConfig.sequence);

        return layerResult;
    }
}
