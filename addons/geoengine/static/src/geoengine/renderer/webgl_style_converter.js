/** @odoo-module native */
import {
    DEFAULT_COLOR,
    isWebGLExpressible,
    RANGED_MODES,
    UNCLASSIFIED_COLOR,
    UNIQUE,
    withOpacity,
} from "../classification.js";
import { savedValue } from "../record_values.js";
import { LABEL_STYLE } from "./geoengine_renderer_styling.js";

/**
 * @param {Object} styling
 * @param {string} attributeField
 * @returns {Array|string|null}
 */
export function createChoroplethExpression(styling, attributeField) {
    if (!styling?.values?.length || !styling?.colors?.length || !attributeField) {
        return null;
    }
    if (!isWebGLExpressible(styling)) {
        return null;
    }

    const value = ["get", attributeField];

    if (styling.mode === UNIQUE) {
        const expression = ["match", value];
        styling.values.forEach((v, i) => {
            expression.push(v, styling.colors[i] || UNCLASSIFIED_COLOR);
        });
        expression.push(UNCLASSIFIED_COLOR);
        return expression;
    }

    if (!RANGED_MODES.has(styling.mode)) {
        return null;
    }

    const lastClass = styling.values.length - 2;
    if (lastClass < 0) {
        return null;
    }
    const expression = ["case"];
    for (let i = 0; i < lastClass; i++) {
        expression.push(["<=", value, styling.values[i + 1]]);
        expression.push(styling.colors[i] || UNCLASSIFIED_COLOR);
    }
    expression.push(styling.colors[lastClass] || UNCLASSIFIED_COLOR);
    return expression;
}

/**
 * @param {Object} styling
 * @param {number} styling.minValue
 * @param {number} styling.maxValue
 * @param {number} styling.minSize
 * @param {number} styling.maxSize
 * @param {string} attributeField
 * @returns {Array|number}
 */
export function createProportionalSizeExpression(styling, attributeField) {
    const minSize = styling.minSize || 5;
    const maxSize = styling.maxSize || 15;
    const minValue = styling.minValue ?? 0;
    const maxValue = styling.maxValue ?? 0;

    if (minValue === maxValue) {
        return (minSize + maxSize) / 2;
    }

    return [
        "interpolate",
        ["linear"],
        ["get", attributeField],
        minValue,
        minSize,
        maxValue,
        maxSize,
    ];
}

/**
 * @param {Object} layerConfig
 * @param {Object|null} styling
 * @param {string} [geometryType='polygon']
 * @returns {Object}
 */
export function createWebGLStyle(layerConfig, styling, geometryType = "polygon") {
    const geoRepr = layerConfig.geo_repr || "basic";
    const attributeField = layerConfig.attribute_field_name;

    const opacity = layerConfig.layer_opacity ?? 1;
    let fillColor;
    const strokeColor = withOpacity("rgba(0, 0, 0, 1)", opacity);
    const strokeWidth = 1;
    let circleRadius = 7;

    switch (geoRepr) {
        case "colored": {
            const expression = createChoroplethExpression(styling, attributeField);
            if (!expression) {
                return {
                    unsupported: true,
                    reason:
                        "this classification cannot be expressed as a WebGL style " +
                        "(a shader has no string type)",
                };
            }
            fillColor = expression;
            break;
        }

        case "proportion":
            fillColor = styling?.color || withOpacity(DEFAULT_COLOR, opacity);
            if (styling && attributeField) {
                circleRadius = createProportionalSizeExpression(
                    styling,
                    attributeField,
                );
            }
            break;

        case "colored_field":
            return {
                unsupported: true,
                reason:
                    "'Color from Field' reads a text field per record, which a " +
                    "WebGL shader cannot do",
            };

        case "basic":
        default:
            fillColor = withOpacity(DEFAULT_COLOR, opacity);
            break;
    }

    const style = {};

    if (geometryType === "point" || geometryType === "multipoint") {
        style["circle-radius"] = circleRadius;
        style["circle-fill-color"] = fillColor;
        style["circle-stroke-color"] = strokeColor;
        style["circle-stroke-width"] = strokeWidth;
    } else if (geometryType.includes("line")) {
        style["stroke-color"] = fillColor;
        style["stroke-width"] = strokeWidth;
    } else {
        style["fill-color"] = fillColor;
        style["stroke-color"] = strokeColor;
        style["stroke-width"] = strokeWidth;
    }

    applyLabelStyle(style, layerConfig);

    return { style };
}

/**
 * @param {Object} style
 * @param {Object} layerConfig
 */
export function applyLabelStyle(style, layerConfig) {
    if (!layerConfig?.display_polygon_labels || !layerConfig.attribute_field_name) {
        return;
    }
    style["text-value"] = ["get", "label"];
    style["text-font"] = LABEL_STYLE.font;
    style["text-fill-color"] = LABEL_STYLE.fillColor;
    style["text-stroke-color"] = LABEL_STYLE.strokeColor;
    style["text-stroke-width"] = LABEL_STYLE.strokeWidth;
    style["text-overflow"] = LABEL_STYLE.overflow;
}

/**
 * @param {Object} layerConfig
 * @param {Object|null} styling
 * @param {string} geometryType
 * @returns {Object}
 */
export function createWebGLStyleWithHighlight(
    layerConfig,
    styling,
    geometryType = "polygon",
) {
    const baseStyle = createWebGLStyle(layerConfig, styling, geometryType);
    if (baseStyle.unsupported) {
        return baseStyle;
    }
    const highlightColor = "rgba(0, 153, 255, 0.8)";

    const isHighlighted = ["==", ["get", "featureId"], ["var", "highlightedId"]];

    const style = baseStyle.style;

    for (const key of ["circle-fill-color", "fill-color", "stroke-color"]) {
        if (style[key] !== undefined) {
            style[key] = ["case", isHighlighted, highlightColor, style[key]];
        }
    }

    return {
        style: style,
        variables: {
            highlightedId: -1,
        },
    };
}

/**
 * @param {Object} layerConfig
 * @param {Array} data
 * @returns {string}
 */
export function detectGeometryType(layerConfig, data) {
    if (data && data.length > 0) {
        const geoFieldName = layerConfig.geo_field_name;
        const firstRecord = data[0];
        const geometry = savedValue(firstRecord, geoFieldName);

        if (geometry) {
            try {
                const geom =
                    typeof geometry === "string" ? JSON.parse(geometry) : geometry;
                const type = geom.type?.toLowerCase() || "";

                if (type.includes("point")) {
                    return "point";
                }
                if (type.includes("line")) {
                    return "line";
                }
                if (type.includes("polygon")) {
                    return "polygon";
                }
            } catch {}
        }
    }

    return "polygon";
}
