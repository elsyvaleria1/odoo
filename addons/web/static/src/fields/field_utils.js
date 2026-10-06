// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { Operation } from "@web/core/utils/operation";

const log = makeLogger("web.fields.utils");

/**
 * @param {Record<string, any>} options
 * @returns {boolean}
 */
export function extractAutosave(options) {
    return "autosave" in options ? exprToBoolean(options.autosave) : true;
}

/**
 * @param {import("@web/model/relational_model/record").RelationalRecord} record
 * @param {string} fieldName
 * @returns {boolean}
 */
export const isFalseEmpty = (record, fieldName) =>
    /** @type {Record<string, any>} */ (record.data)[fieldName] === false;

const PIXEL_DIMENSION = /^\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*$/i;

/**
 * Pixels only: every consumer sizes a fixed box in px, so a relative unit
 * ("10%", "2em") yields no constraint rather than the same number of pixels.
 * @param {unknown} value
 * @returns {number | undefined}
 */
export function parseDimensionAttr(value) {
    if (value === undefined || value === null || value === "") {
        return undefined;
    }
    if (typeof value === "number") {
        return Number.isFinite(value) && value >= 0 ? value : undefined;
    }
    const match = PIXEL_DIMENSION.exec(String(value));
    const parsed = match ? Number(match[1]) : undefined;
    log.logic("dimension", () => ({ value, pixels: parsed }));
    return parsed;
}

/**
 * @param {{ attrs: Record<string, any>, options: Record<string, any> }} node
 * @returns {{ width: number | undefined, height: number | undefined }}
 */
export function extractImageDimensions({ attrs, options }) {
    const size = options.size;
    const dimensions = size
        ? {
              width: parseDimensionAttr(size[0]) || undefined,
              height: parseDimensionAttr(size[1]) || undefined,
          }
        : {
              width: parseDimensionAttr(attrs.width),
              height: parseDimensionAttr(attrs.height),
          };
    log.logic("image dimensions", () => ({
        size,
        width: attrs.width,
        height: attrs.height,
        source: size ? "size option" : "attributes",
        ...dimensions,
    }));
    return dimensions;
}

/**
 * @param {Record<string, any>} options
 * @returns {boolean}
 */
export function extractFormatNumber(options) {
    return options?.enable_formatting !== undefined
        ? Boolean(options.enable_formatting)
        : true;
}

/**
 * @param {{ options: Record<string, any> }} params
 * @returns {{ formatNumber: boolean, humanReadable: boolean, inputType: string | undefined, step: number | undefined, decimals: number }}
 */
export function extractNumericOptions({ options }) {
    return {
        formatNumber: extractFormatNumber(options),
        humanReadable: !!options.human_readable,
        inputType: options.type,
        step: options.step,
        decimals: options.decimals || 0,
    };
}

/**
 * @template {number | Operation} T
 * @param {T} parsed
 * @param {number} divisor
 * @returns {T}
 */
export function unscaleParsedNumber(parsed, divisor) {
    if (parsed instanceof Operation) {
        if (parsed.operator === "+" || parsed.operator === "-") {
            return /** @type {T} */ (
                new Operation(parsed.operator, parsed.operand / divisor)
            );
        }
        return parsed;
    }
    return /** @type {T} */ (/** @type {number} */ (parsed) / divisor);
}

/**
 * @param {import("@web/model/relational_model/record").RelationalRecord} record
 * @param {{ valueField: string, fileNameField?: string, data?: string | false, name?: string }} params
 * @returns {Promise<void>}
 */
export function updateFileValue(record, { valueField, fileNameField, data, name }) {
    /** @type {Record<string, any>} */
    const changes = { [valueField]: data || false };
    const fields = /** @type {Record<string, any>} */ (record.fields);
    if (fileNameField && fileNameField in fields) {
        const nextName = name || false;
        if (
            /** @type {Record<string, any>} */ (record.data)[fileNameField] !== nextName
        ) {
            changes[fileNameField] = nextName;
        }
    }
    return record.update(changes);
}
