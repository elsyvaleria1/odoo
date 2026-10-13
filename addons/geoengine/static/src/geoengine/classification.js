/** @odoo-module native */

import { serializeDate, serializeDateTime } from "@web/core/l10n/dates";
import { escape } from "@web/core/utils/format/strings";

export const UNIQUE = "unique";
export const QUANTILE = "quantile";
export const INTERVAL = "interval";

export const RANGED_MODES = new Set([QUANTILE, INTERVAL]);

export const DEFAULT_COLOR = "rgba(51, 136, 255, 1)";
export const DEFAULT_TRAIL_COLOR = "#3366FF";
export const UNCLASSIFIED_COLOR = "rgba(204, 204, 204, 0.55)";
export const DEFAULT_MIN_SIZE = 5;

export { withOpacity } from "@web/core/colors/colors";

/**
 * @param {*} value
 * @returns {number}
 */
export function valueHash(value) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
        return numeric;
    }
    let hash = 0;
    for (const char of String(value)) {
        hash = (hash * 31 + char.codePointAt(0)) % 2147483647;
    }
    return hash;
}

/**
 * @param {*} value
 * @returns {*}
 */
export function classValue(value) {
    if (value === false || value === null || value === undefined || value === "") {
        return null;
    }
    if (value instanceof Temporal.PlainDate) {
        return serializeDate(value);
    }
    if (value instanceof Temporal.ZonedDateTime) {
        return serializeDateTime(value);
    }
    return value;
}

/**
 * @param {Object} chromaColor
 * @returns {string}
 */
export function toRgbaString(chromaColor) {
    const [r, g, b, a] = chromaColor.rgba();
    return `rgba(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}, ${a})`;
}

/**
 * @param {Object} styling
 * @param {string} styling.mode
 * @param {Array} styling.values
 * @param {Array<string>} styling.colors
 * @param {*} value
 * @returns {number}
 */
export function classIndexFor(styling, value) {
    if (!styling || !styling.values || !styling.values.length) {
        return -1;
    }
    if (styling.mode === UNIQUE) {
        return styling.values.indexOf(value);
    }
    if (!RANGED_MODES.has(styling.mode)) {
        return -1;
    }
    const lastClass = styling.values.length - 2;
    if (lastClass < 0) {
        return -1;
    }
    if (typeof styling.values[0] !== "number") {
        return -1;
    }
    if (typeof value !== "number" && typeof value !== "string") {
        return -1;
    }
    const numeric = typeof value === "number" ? value : Number(value.trim() || NaN);
    if (!Number.isFinite(numeric)) {
        return -1;
    }
    for (let i = 0; i <= lastClass; i++) {
        if (numeric <= styling.values[i + 1]) {
            return i;
        }
    }
    return lastClass;
}

/**
 * @param {Object} styling
 * @param {*} value
 * @returns {string|null}
 */
export function classColorFor(styling, value) {
    const index = classIndexFor(styling, classValue(value));
    return index === -1 ? null : styling.colors[index] || null;
}

/**
 * @param {Object} styling
 * @returns {boolean}
 */
export function isWebGLExpressible(styling) {
    if (!styling || !styling.values || !styling.values.length) {
        return false;
    }
    return styling.values.every((v) => typeof v === "number" && Number.isFinite(v));
}

/**
 * @param {string} title
 * @param {Array<string|number>} labels
 * @param {string[]} colors
 * @returns {string}
 */
export function legendHtml(title, labels, colors) {
    const rows = labels.map(
        (label, i) =>
            `<div><div class="geostats-legend-block" style="background-color:${escape(
                colors[i],
            )}"></div> ${escape(String(label))}</div>`,
    );
    return `<div class="geostats-legend"><div class="geostats-legend-title">${escape(
        title,
    )}</div>${rows.join("")}</div>`;
}

/**
 * @param {{minValue: number, maxValue: number, minSize: number, maxSize: number}} styling
 * @param {*} value
 * @returns {number}
 */
export function proportionalRadius(styling, value) {
    const { minValue, maxValue, minSize, maxSize } = styling;
    const number = typeof value === "number" ? value : NaN;
    if (!Number.isFinite(number)) {
        return minSize;
    }
    const range = maxValue - minValue;
    const proportion =
        range > 0 ? Math.min(Math.max((number - minValue) / range, 0), 1) : 0.5;
    return minSize + proportion * (maxSize - minSize);
}

/**
 * @param {Object} layerConfig
 * @returns {boolean}
 */
export function needsPopulationBounds(layerConfig) {
    if (!layerConfig || !layerConfig.attribute_field_name) {
        return false;
    }
    if (layerConfig.geo_repr === "proportion") {
        return true;
    }
    return (
        layerConfig.geo_repr === "colored" && layerConfig.classification === INTERVAL
    );
}

/**
 * @param {Object} layerConfig
 * @returns {boolean}
 */
export function needsPopulationValues(layerConfig) {
    if (!layerConfig || !layerConfig.attribute_field_name) {
        return false;
    }
    return (
        layerConfig.geo_repr === "colored" &&
        (layerConfig.classification === QUANTILE ||
            layerConfig.classification === UNIQUE)
    );
}
