/** @odoo-module native */

import { LruCache } from "@web/core/utils/lru_cache";

import { ol } from "../../lib/geo_libs.js";
import {
    classColorFor,
    DEFAULT_COLOR,
    proportionalRadius,
    UNCLASSIFIED_COLOR,
    withOpacity,
} from "../classification.js";
import { savedValue } from "../record_values.js";

const STYLE_CACHE_SIZE = 2000;

export const LABEL_STYLE = {
    font: "12px Calibri,sans-serif",
    fillColor: "#000",
    strokeColor: "#fff",
    strokeWidth: 2,
    overflow: true,
};

/**
 * @param {Object} record
 * @param {Object} layerConfig
 * @returns {string|null}
 */
export function labelValueFor(record, layerConfig) {
    if (!layerConfig?.display_polygon_labels) {
        return null;
    }
    const field = layerConfig.attribute_field_name;
    const value = field ? savedValue(record, field) : null;
    if (value === undefined || value === null || value === false || value === "") {
        return null;
    }
    return String(value);
}

export class GeoengineRendererStyling {
    /**
     * @param {GeoengineRenderer} renderer
     */
    constructor(renderer) {
        this.renderer = renderer;
        this._styleCache = new LruCache(STYLE_CACHE_SIZE);
    }

    /**
     * @param {Object} layerConfig
     * @param {Array} data
     * @param {Object|null} styling
     * @param {ol.layer.Vector} vectorLayer
     */
    applyStyleToLayer(layerConfig, data, styling, vectorLayer) {
        let styleFunction;
        let legendHTML;

        if (layerConfig.geo_repr === "colored" && styling) {
            styleFunction = this._createChoroplethStyle(styling, layerConfig);
            legendHTML = styling.legend;
        } else if (layerConfig.geo_repr === "colored_field") {
            styleFunction = this._createColoredFieldStyle(layerConfig);
            legendHTML = null;
        } else if (layerConfig.geo_repr === "proportion" && styling) {
            styleFunction = this._createProportionalStyle(styling, layerConfig);
            legendHTML = null;
        } else {
            styleFunction = this._createDefaultStyle(layerConfig);
            legendHTML = null;
        }

        vectorLayer.setStyle(styleFunction);

        if (legendHTML) {
            this.initLegend({ legend: legendHTML }, layerConfig);
        }
    }

    /**
     * @param {Object} styling
     * @param {Array<number>} styling.values
     * @param {Array<string>} styling.colors
     * @param {string} styling.indicator
     * @param {Object} layerConfig
     * @returns {Function}
     */
    _createChoroplethStyle(styling, layerConfig) {
        const { indicator } = styling;

        return (feature) => {
            const record = feature.get("record");
            if (!record) {
                return this._getDefaultStyle({});
            }

            const attributeValue = savedValue(record, indicator);
            const color = classColorFor(styling, attributeValue) || UNCLASSIFIED_COLOR;
            const geometryType = feature.getGeometry()?.getType();

            return this._getStyleForGeometryType(geometryType, {
                fillColor: color,
                strokeColor: "#000",
                strokeWidth: 1,
                pointRadius: 7,
                label: labelValueFor(record, layerConfig),
            });
        };
    }

    /**
     * @param {ol.style.Style} style
     * @param {Object} record
     * @param {Object} layerConfig
     */
    _applyLabel(style, record, layerConfig) {
        const value = labelValueFor(record, layerConfig);
        if (value !== null) {
            style.setText(this._labelText(value));
        }
    }

    /**
     * @param {Object} styling
     * @param {string} styling.color
     * @param {string} styling.indicator
     * @param {number} styling.minValue
     * @param {number} styling.maxValue
     * @param {number} styling.minSize
     * @param {number} styling.maxSize
     * @param {Object} layerConfig
     * @returns {Function}
     */
    _createProportionalStyle(styling, layerConfig) {
        const { color, indicator } = styling;

        return (feature) => {
            const record = feature.get("record");
            if (!record) {
                return this._getDefaultStyle({});
            }

            const attributeValue = savedValue(record, indicator);
            const radius = proportionalRadius(styling, attributeValue);

            const style = new ol.style.Style({
                image: new ol.style.Circle({
                    radius: radius,
                    fill: new ol.style.Fill({ color: color }),
                    stroke: new ol.style.Stroke({ color: "#000", width: 1 }),
                }),
                fill: new ol.style.Fill({ color: color }),
                stroke: new ol.style.Stroke({ color: "#000", width: 1 }),
            });
            this._applyLabel(style, record, layerConfig);
            return style;
        };
    }

    /**
     * @param {Object} config
     * @returns {Function}
     */
    _createDefaultStyle(config) {
        const fillColor = config.begin_color || DEFAULT_COLOR;
        const opacity = config.layer_opacity !== undefined ? config.layer_opacity : 1;

        return (feature) => {
            const geometryType = feature.getGeometry()?.getType();
            return this._getStyleForGeometryType(geometryType, {
                fillColor: fillColor,
                strokeColor: "#000",
                strokeWidth: 2,
                pointRadius: 7,
                opacity: opacity,
                label: labelValueFor(feature.get("record"), config),
            });
        };
    }

    /**
     * @param {Object} config
     * @param {string} config.color_field_name
     * @param {string} [config.begin_color]
     * @param {number} [config.layer_opacity]
     * @returns {Function}
     */
    _createColoredFieldStyle(config) {
        const colorFieldName = config.color_field_name;
        const fallbackColor = config.begin_color || DEFAULT_COLOR;
        const opacity = config.layer_opacity !== undefined ? config.layer_opacity : 1;

        const hexColorPattern = /^#(?:[0-9a-fA-F]{3}){1,2}$/;

        return (feature) => {
            const record = feature.get("record");
            let fillColor = fallbackColor;

            if (record && colorFieldName) {
                const colorValue = savedValue(record, colorFieldName);
                if (colorValue && hexColorPattern.test(colorValue)) {
                    fillColor = colorValue;
                }
            }

            const geometryType = feature.getGeometry()?.getType();
            return this._getStyleForGeometryType(geometryType, {
                fillColor: fillColor,
                strokeColor: fillColor,
                strokeWidth: 5,
                pointRadius: 7,
                opacity: opacity,
                label: labelValueFor(record, config),
            });
        };
    }

    /**
     * @param {string} geometryType
     * @param {Object} options
     * @returns {ol.style.Style}
     */
    _getStyleForGeometryType(geometryType, options) {
        const { strokeWidth, pointRadius, opacity } = options;
        const fillColor = withOpacity(options.fillColor, opacity);
        const strokeColor = withOpacity(options.strokeColor, opacity);
        const key = `${geometryType}|${fillColor}|${strokeColor}|${strokeWidth}|${pointRadius}|${options.label ?? ""}`;
        const cached = this._styleCache.get(key);
        if (cached) {
            return cached;
        }

        const styleConfig = {
            fill: new ol.style.Fill({ color: fillColor }),
            stroke: new ol.style.Stroke({
                color: strokeColor,
                width: strokeWidth,
            }),
        };

        if (geometryType === "Point" || geometryType === "MultiPoint") {
            styleConfig.image = new ol.style.Circle({
                radius: pointRadius,
                fill: styleConfig.fill,
                stroke: styleConfig.stroke,
            });
        }

        const style = new ol.style.Style(styleConfig);
        if (options.label) {
            style.setText(this._labelText(options.label));
        }
        this._styleCache.set(key, style);
        return style;
    }

    /**
     * @param {string} value
     * @returns {ol.style.Text}
     */
    _labelText(value) {
        return new ol.style.Text({
            text: value,
            fill: new ol.style.Fill({ color: LABEL_STYLE.fillColor }),
            stroke: new ol.style.Stroke({
                color: LABEL_STYLE.strokeColor,
                width: LABEL_STYLE.strokeWidth,
            }),
            font: LABEL_STYLE.font,
            overflow: LABEL_STYLE.overflow,
        });
    }

    /**
     * @param {Object} config
     * @returns {ol.style.Style}
     */
    _getDefaultStyle(config) {
        return new ol.style.Style({
            fill: new ol.style.Fill({
                color: config.fillColor || DEFAULT_COLOR,
            }),
            stroke: new ol.style.Stroke({
                color: config.strokeColor || "#000",
                width: config.strokeWidth || 1,
            }),
            image: new ol.style.Circle({
                radius: config.pointRadius || 7,
                fill: new ol.style.Fill({
                    color: config.fillColor || DEFAULT_COLOR,
                }),
                stroke: new ol.style.Stroke({
                    color: config.strokeColor || "#000",
                    width: 1,
                }),
            }),
        });
    }

    /**
     * @param {Object} styleInfo
     * @param {string} styleInfo.legend
     * @param {Object} layerConfig
     */
    initLegend(styleInfo, layerConfig) {
        const parentContainer = this.renderer.legendRef.el;
        if (!parentContainer) {
            return;
        }

        const legendId = "legend-" + layerConfig.resId;
        const existingLegend = parentContainer.querySelector(
            `#${CSS.escape(legendId)}`,
        );

        if (existingLegend) {
            if (styleInfo.legend) {
                existingLegend.innerHTML = styleInfo.legend;
                existingLegend.style.display = layerConfig.isVisible ? "block" : "none";
            }
        } else {
            if (styleInfo.legend && styleInfo.legend !== "") {
                const containerLegend = document.createElement("div");
                containerLegend.innerHTML = styleInfo.legend;
                containerLegend.setAttribute("id", legendId);
                containerLegend.className = "legend";
                containerLegend.style.display = layerConfig.isVisible
                    ? "block"
                    : "none";
                parentContainer.appendChild(containerLegend);
            }
        }
    }

    /**
     * @param {number|string} layerResId
     * @param {boolean} visible
     */
    toggleLegend(layerResId, visible) {
        const legendEl = this.renderer.legendRef.el?.querySelector(
            `#${CSS.escape("legend-" + layerResId)}`,
        );
        if (legendEl) {
            legendEl.style.display = visible ? "block" : "none";
        }
    }

    /**
     * @param {Array<number|string>} liveResIds
     */
    pruneLegends(liveResIds) {
        const container = this.renderer.legendRef.el;
        if (!container) {
            return;
        }
        const live = new Set(liveResIds.map(String));
        for (const element of container.querySelectorAll("[id^='legend-']")) {
            if (!live.has(element.id.slice("legend-".length))) {
                this.removeLegend(element.id.slice("legend-".length));
            }
        }
    }

    /**
     * @param {number|string} layerResId
     */
    removeLegend(layerResId) {
        const legendEl = this.renderer.legendRef.el?.querySelector(
            `#${CSS.escape("legend-" + layerResId)}`,
        );
        if (legendEl && legendEl.parentNode) {
            legendEl.parentNode.removeChild(legendEl);
        }
    }

    /**
     * @param {ol.Feature} feature
     * @returns {ol.style.Style}
     */
    selectStyle(feature) {
        const geometryType = feature.getGeometry().getType();
        switch (geometryType) {
            case "Point":
            case "MultiPoint":
                return new ol.style.Style({
                    image: new ol.style.Circle({
                        radius: 3 * 2,
                        fill: new ol.style.Fill({
                            color: [0, 153, 255, 1],
                        }),
                        stroke: new ol.style.Stroke({
                            color: [255, 255, 255, 1],
                            width: 3 / 2,
                        }),
                    }),
                    zIndex: Infinity,
                });
            case "Polygon":
            case "MultiPolygon": {
                return new ol.style.Style({
                    fill: new ol.style.Fill({ color: [0, 153, 255, 0.4] }),
                    stroke: new ol.style.Stroke({
                        color: [0, 153, 255, 1],
                        width: 2,
                    }),
                });
            }
            case "LineString":
            case "MultiLineString":
                return new ol.style.Style({
                    stroke: new ol.style.Stroke({
                        color: [0, 153, 255, 1],
                        width: 4,
                    }),
                });
            default:
                return new ol.style.Style({
                    fill: new ol.style.Fill({
                        color: [0, 153, 255, 0.4],
                    }),
                    stroke: new ol.style.Stroke({
                        color: [0, 153, 255, 1],
                        width: 2,
                    }),
                });
        }
    }
}
