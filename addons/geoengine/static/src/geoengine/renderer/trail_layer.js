/** @odoo-module native */
import { makeGeoLogger } from "../../geo_debug.js";
import { ol } from "../../lib/geo_libs.js";
import { DEFAULT_TRAIL_COLOR } from "../classification.js";
import { savedValue, savedValues } from "../record_values.js";
import { detectGeoJSONProjection } from "./geoengine_renderer_utils.js";

const debugLog = makeGeoLogger("TrailLayer");

export class TrailLayerBuilder {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @returns {ol.layer.WebGLVector|null}
     */
    createWebGLTrailLayer(layerConfig, data) {
        debugLog("createWebGLTrailLayer() - Creating WebGL layer:", {
            name: layerConfig.name,
            dataCount: data?.length || 0,
        });

        if (typeof ol.layer.WebGLVector === "undefined") {
            console.warn(
                "[GeoengineRendererLayers] WebGLVector not available, falling back to regular Vector",
            );
            return null;
        }

        const archInfo = this.renderer.props.archInfo || {};
        const timestampsField = archInfo.trailTimestampsField || "trail_timestamps";
        const colorField = archInfo.trailColorField || "trail_color";

        let minTimestamp = Infinity;
        let maxTimestamp = -Infinity;

        for (const item of data) {
            const timestampsJson = savedValue(item, timestampsField);
            if (timestampsJson) {
                try {
                    const timestamps = JSON.parse(timestampsJson);
                    if (timestamps.length > 0) {
                        minTimestamp = Math.min(minTimestamp, timestamps[0]);
                        maxTimestamp = Math.max(
                            maxTimestamp,
                            timestamps[timestamps.length - 1],
                        );
                    }
                } catch (_e) {
                    debugLog("Error parsing timestamps:", _e);
                }
            }
        }

        if (minTimestamp === Infinity || maxTimestamp === -Infinity) {
            debugLog("No valid timestamps found for WebGL layer");
            return null;
        }

        debugLog("WebGL trail time range:", {
            min: new Date(minTimestamp * 1000).toISOString(),
            max: new Date(maxTimestamp * 1000).toISOString(),
        });

        const vectorSource = new ol.source.Vector();
        this._addWebGLTrailFeatures(
            data,
            layerConfig,
            vectorSource,
            timestampsField,
            colorField,
        );

        const firstTrailColor = savedValue(data[0], colorField) || DEFAULT_TRAIL_COLOR;

        const webglLayer = new ol.layer.WebGLVector({
            source: vectorSource,
            title: layerConfig.name,
            layerId: layerConfig.resId,
            style: this._createWebGLTimeStyle(),
            variables: {
                currentTime: maxTimestamp,
            },
        });

        webglLayer.setZIndex(layerConfig.sequence);

        return {
            layer: webglLayer,
            minTimestamp: minTimestamp,
            maxTimestamp: maxTimestamp,
            trailColor: firstTrailColor,
        };
    }

    /**
     * @param {Array} data
     * @param {Object} layerConfig
     * @param {ol.source.Vector} vectorSource
     * @param {string} timestampsField
     * @param {string} colorField
     */
    _addWebGLTrailFeatures(
        data,
        layerConfig,
        vectorSource,
        timestampsField,
        colorField,
    ) {
        const mapProjection = this.renderer.map.getView().getProjection();
        const defaultColor = DEFAULT_TRAIL_COLOR;

        for (const item of data) {
            const values = savedValues(item);
            const jsonGeometry = values[layerConfig.geo_field_name];
            const timestampsJson = values[timestampsField];
            if (!jsonGeometry || !timestampsJson) {
                continue;
            }

            const trailColor = values[colorField] || defaultColor;

            let timestamps;
            try {
                timestamps = JSON.parse(timestampsJson);
            } catch {
                continue;
            }

            const dataProjection = detectGeoJSONProjection(jsonGeometry);
            const baseGeometry = this.renderer.format.readGeometry(jsonGeometry, {
                dataProjection: dataProjection,
                featureProjection: mapProjection,
            });

            const parts = this._trailParts(baseGeometry);
            if (!parts.length) {
                debugLog(
                    "Skipping geometry with no line parts:",
                    baseGeometry.getType(),
                );
                continue;
            }

            const totalVertices = parts.reduce((n, part) => n + part.length, 0);
            if (totalVertices !== timestamps.length) {
                debugLog("Coordinate/timestamp mismatch:", {
                    coords: totalVertices,
                    timestamps: timestamps.length,
                });
                timestamps = this._interpolateTimestamps(timestamps, totalVertices);
            }

            let consumed = 0;
            const xymParts = parts.map((part) => {
                const xym = part.map((coord, i) => [
                    coord[0],
                    coord[1],
                    timestamps[consumed + i],
                ]);
                consumed += part.length;
                return xym;
            });
            const xymGeometry =
                xymParts.length === 1
                    ? new ol.geom.LineString(xymParts[0], "XYM")
                    : new ol.geom.MultiLineString(xymParts, "XYM");

            const attributes = { ...values };
            const featureId = item.resId || item.id || values.id;
            if (!attributes.id && featureId) {
                attributes.id = featureId;
            }

            delete attributes[layerConfig.geo_field_name];
            delete attributes[timestampsField];

            const feature = new ol.Feature({
                geometry: xymGeometry,
                trail_color: trailColor,
                attributes: attributes,
                model: layerConfig.model,
            });

            if (featureId) {
                feature.setId(featureId);
            }

            vectorSource.addFeature(feature);
        }
    }

    /**
     * @param {ol.geom.Geometry} geometry
     * @returns {Array<Array<number[]>>}
     */
    _trailParts(geometry) {
        const type = geometry.getType();
        const parts =
            type === "LineString"
                ? [geometry.getCoordinates()]
                : type === "MultiLineString"
                  ? geometry.getCoordinates()
                  : [];
        return parts.filter((part) => part.length > 1);
    }

    /**
     * @param {number[]} timestamps
     * @param {number} targetCount
     * @returns {number[]}
     */
    _interpolateTimestamps(timestamps, targetCount) {
        if (timestamps.length === targetCount) {
            return timestamps;
        }
        if (timestamps.length < 2) {
            return new Array(targetCount).fill(timestamps[0] || 0);
        }

        const result = [];
        const sourceStep = (timestamps.length - 1) / (targetCount - 1);

        for (let i = 0; i < targetCount; i++) {
            const sourceIndex = i * sourceStep;
            const lowerIndex = Math.floor(sourceIndex);
            const upperIndex = Math.min(lowerIndex + 1, timestamps.length - 1);
            const fraction = sourceIndex - lowerIndex;

            const interpolated =
                timestamps[lowerIndex] +
                fraction * (timestamps[upperIndex] - timestamps[lowerIndex]);
            result.push(Math.round(interpolated));
        }

        return result;
    }

    /**
     * @returns {Object}
     */
    _createWebGLTimeStyle() {
        return [
            {
                style: {
                    "stroke-width": 5,
                    "stroke-color": ["get", "trail_color"],
                },
                filter: ["<=", ["line-metric"], ["var", "currentTime"]],
            },
        ];
    }

    /**
     * @param {ol.layer.WebGLVector} layer
     * @param {number} timestamp
     */
    updateWebGLLayerTime(layer, timestamp) {
        if (layer && typeof layer.updateStyleVariables === "function") {
            layer.updateStyleVariables({ currentTime: timestamp });
        }
    }
}
