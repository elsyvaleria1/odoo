// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import { localization as l10n } from "@web/core/l10n/localization";
import { _t } from "@web/core/translation";
import { intersperse } from "@web/core/utils/format/strings";

const log = makeLogger("web.core.numbers");

/**
 * @param {number} num
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
export function clamp(num, min, max) {
    return Math.max(Math.min(num, max), min);
}

/**
 * @param {number} start
 * @param {number} stop
 * @param {number} step
 * @returns {number[]}
 */
export function range(start, stop, step = 1) {
    if (step === 0) {
        throw new Error("range() step argument must not be zero");
    }
    const array = [];
    const nsteps = Math.ceil((stop - start) / step);
    for (let i = 0; i < nsteps; i++) {
        array.push(start + step * i);
    }
    return array;
}

/**
 * @param {number} value
 * @returns {number}
 */
function roundHalfAwayFromZero(value) {
    const magnitude = Math.abs(value);
    if (Math.round(magnitude + 1) - Math.round(magnitude) !== 1) {
        return value + Math.sign(value) * 0.5;
    }
    return Math.round(magnitude) * Math.sign(value);
}

const EPSILON_SCALE = 2 ** -50;
// Past 2**47 the epsilon grows beyond an eighth of a step and the float's own
// representation error can fake a tie: the float stops telling real digits from
// noise, so the shortest decimal that round-trips to it is rounded instead.
const EXACT_THRESHOLD = 2 ** 47;
// a double round-trips any decimal of at most this many significant digits
const FAITHFUL_DIGITS = 15;

/**
 * @param {number} value
 * @returns {[bigint, number]}
 */
function shortestDecimal(value) {
    const [mantissa, exponent] = value.toExponential().split("e");
    const [whole, fraction = ""] = mantissa.split(".");
    return [BigInt(whole + fraction), Number(exponent) - fraction.length];
}

/**
 * @param {number} value
 * @returns {number}
 */
function significantDigits(value) {
    return Math.abs(value).toExponential().split("e")[0].replace(".", "").length;
}

/**
 * @param {number} magnitude
 * @param {number} roundingFactor
 * @param {boolean} inverted
 * @returns {number}
 */
function tie(magnitude, roundingFactor, inverted) {
    if (!Number.isInteger(roundingFactor)) {
        return NaN;
    }
    const halves = 2 * Math.floor(magnitude) + 1;
    return inverted ? halves / (2 * roundingFactor) : (halves * roundingFactor) / 2;
}

/**
 * @param {number} value
 * @param {number} step
 * @param {"HALF-UP" | "HALF-DOWN" | "HALF-EVEN" | "UP" | "DOWN"} method
 * @returns {number}
 */
function roundExact(value, step, method) {
    const [valueDigits, valueExponent] = shortestDecimal(Math.abs(value));
    const [stepDigits, stepExponent] = shortestDecimal(step);
    const shift = valueExponent - stepExponent;
    const numerator = shift >= 0 ? valueDigits * 10n ** BigInt(shift) : valueDigits;
    const denominator = shift >= 0 ? stepDigits : stepDigits * 10n ** BigInt(-shift);
    const quotient = numerator / denominator;
    const twiceRemainder = 2n * (numerator % denominator);
    let carry;
    switch (method) {
        case "HALF-UP": {
            carry = twiceRemainder >= denominator;
            break;
        }
        case "HALF-EVEN": {
            carry =
                twiceRemainder > denominator ||
                (twiceRemainder === denominator && quotient % 2n === 1n);
            break;
        }
        case "HALF-DOWN": {
            carry = twiceRemainder > denominator;
            break;
        }
        case "UP": {
            carry = twiceRemainder > 0n;
            break;
        }
        case "DOWN": {
            carry = false;
            break;
        }
        default: {
            throw new Error(`Unknown rounding method: ${method}`);
        }
    }
    const rounded = Number(
        `${(quotient + (carry ? 1n : 0n)) * stepDigits}e${stepExponent}`,
    );
    return rounded === 0 ? 0 : Math.sign(value) * rounded;
}

/**
 * @param {number} value
 * @param {number} precision
 * @param {"HALF-UP" | "HALF-DOWN" | "HALF-EVEN" | "UP" | "DOWN"} [method="HALF-UP"]
 */
export function roundPrecision(value, precision, method = "HALF-UP") {
    if (value === 0) {
        return 0;
    }
    if (typeof value !== "number" || !Number.isFinite(value)) {
        return NaN;
    }
    if (!precision || precision < 0 || !Number.isFinite(precision)) {
        precision = 1;
    }
    let roundingFactor = precision;
    let normalize = (/** @type {number} */ val) => val / roundingFactor;
    let denormalize = (/** @type {number} */ val) => val * roundingFactor;
    const inverted = roundingFactor < 1;
    if (inverted) {
        roundingFactor = invertFloat(roundingFactor);
        [normalize, denormalize] = [denormalize, normalize];
    }
    const normalizedValue = normalize(value);
    if (normalizedValue === 0) {
        return 0;
    }
    const magnitude = Math.abs(normalizedValue);
    if (!(magnitude < EXACT_THRESHOLD)) {
        return roundExact(value, precision, method);
    }
    const sign = Math.sign(normalizedValue);
    const epsilon = magnitude * EPSILON_SCALE;
    const fraction = magnitude % 1;
    const nearBoundary =
        method === "UP" || method === "DOWN"
            ? fraction < 2 * epsilon || fraction > 1 - 2 * epsilon
            : Math.abs(fraction - 0.5) < 2 * epsilon;
    let roundedValue;

    switch (method) {
        case "DOWN": {
            roundedValue = Math.trunc(normalizedValue + sign * epsilon);
            break;
        }
        case "HALF-DOWN": {
            const integral = Math.floor(Math.abs(normalizedValue));
            const remainder = Math.abs(normalizedValue) - integral;
            const isHalf = remainder === 0.5 || Math.abs(0.5 - remainder) < epsilon;
            roundedValue = isHalf
                ? sign * integral
                : roundHalfAwayFromZero(normalizedValue - sign * epsilon);
            break;
        }
        case "HALF-UP": {
            roundedValue = roundHalfAwayFromZero(normalizedValue + sign * epsilon);
            break;
        }
        case "HALF-EVEN": {
            const integral = Math.floor(normalizedValue);
            const remainder = Math.abs(normalizedValue - integral);
            const isHalf = remainder === 0.5 || Math.abs(0.5 - remainder) < epsilon;
            roundedValue = isHalf
                ? integral + (integral & 1)
                : roundHalfAwayFromZero(normalizedValue);
            break;
        }
        case "UP": {
            roundedValue = Math.trunc(normalizedValue + sign * (1 - epsilon));
            break;
        }
        default: {
            throw new Error(`Unknown rounding method: ${method}`);
        }
    }

    const result = denormalize(roundedValue);
    if (
        nearBoundary &&
        result !== value &&
        (method === "UP" ||
            method === "DOWN" ||
            Math.abs(value) !== tie(magnitude, roundingFactor, inverted)) &&
        significantDigits(value) <= FAITHFUL_DIGITS
    ) {
        // the epsilon decided it, but the float spells a decimal off the
        // boundary: a real digit, not arithmetic noise, so round that instead
        return roundExact(value, precision, method);
    }
    return result === 0 ? 0 : result;
}

/**
 * @param {number} value
 * @param {number} decimals
 * @returns {string}
 */
function formatFixedDecimals(value, decimals) {
    if (Math.abs(value) >= 1e21) {
        return String(value);
    }
    const rounded = roundDecimals(value, decimals);
    return rounded.toFixed(decimals);
}

const NEGATIVE_POWERS_OF_TEN = Object.freeze([
    1, 1e-1, 1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 1e-7, 1e-8, 1e-9, 1e-10, 1e-11, 1e-12, 1e-13,
    1e-14, 1e-15,
]);

/**
 * @param {number} value
 * @param {number} decimals
 * @returns {number}
 */
export function roundDecimals(value, decimals) {
    const precision = NEGATIVE_POWERS_OF_TEN[decimals] ?? parseFloat("1e" + -decimals);
    return roundPrecision(value, precision);
}

/**
 * @param {number} value
 * @param {number} decimals
 * @returns {boolean}
 */
export function floatIsZero(value, decimals) {
    return value === 0 || roundDecimals(value, decimals) === 0;
}

/**
 * @param {string} number
 * @param {string | false} [thousandsSep=","]
 * @param {number[]} [grouping=[]]
 * @returns {string}
 */
export function insertThousandsSep(number, thousandsSep = ",", grouping = []) {
    const negative = number[0] === "-";
    number = negative ? number.slice(1) : number;
    return (negative ? "-" : "") + intersperse(number, grouping, thousandsSep);
}

/**
 * @param {number} number
 * @param {Object} [options]
 * @param {number} [options.decimals=0]
 * @param {number} [options.minIntegerDigits=1]
 * @param {boolean} [options.trailingZeros=true]
 * @returns {string}
 */
export function humanNumber(number, options = {}) {
    const decimals = options.decimals || 0;
    const minIntegerDigits = options.minIntegerDigits || 1;
    const d2 = 10 ** decimals;
    const numberMagnitude = Number(number.toExponential().split("e")[1]);
    number = roundDecimals(number, decimals);
    if (numberMagnitude >= 21) {
        number = Math.round(number * 10 ** (decimals - numberMagnitude)) / d2;
        return `${number}e+${numberMagnitude}`;
    }
    const unitSymbols = _t("kMGTPE").toString();
    const sign = Math.sign(number);
    number = Math.abs(number);
    let symbol = "";
    const minMagnitude = 10 ** (minIntegerDigits - 1);
    for (let i = unitSymbols.length; i > 0; i--) {
        const s = 10 ** (i * 3);
        if (s <= number / minMagnitude) {
            number = Math.round((number * d2) / s) / d2;
            if (i < unitSymbols.length && number >= 1000 * minMagnitude) {
                // rounding carried into the next unit: 999_999 is "1M", not "1,000k"
                log.logic("humanNumber carried into the next unit", () => ({
                    rounded: number,
                    from: unitSymbols[i - 1],
                    to: unitSymbols[i],
                }));
                number /= 1000;
                i++;
            }
            symbol = unitSymbols[i - 1];
            break;
        }
    }
    const { decimalPoint, grouping, thousandsSep } = l10n;

    const decimalsToKeep = number >= 1000 ? 0 : decimals;
    number = sign * number;
    const [integerPart, fixedDecimalPart] = formatFixedDecimals(
        number,
        decimalsToKeep,
    ).split(".");
    const decimalPart =
        options.trailingZeros === false
            ? fixedDecimalPart?.replace(/0+$/, "")
            : fixedDecimalPart;
    const int = insertThousandsSep(integerPart, thousandsSep, grouping);
    if (!decimalPart) {
        return int + symbol;
    }
    return int + decimalPoint + decimalPart + symbol;
}

/**
 * @param {number} value
 * @param {Object} [options]
 * @param {number[]} [options.digits]
 * @param {number} [options.minDigits]
 * @param {number} [options.minIntegerDigits]
 * @param {boolean} [options.humanReadable]
 * @param {string} [options.decimalPoint]
 * @param {string} [options.thousandsSep]
 * @param {number[]} [options.grouping]
 * @param {number} [options.decimals]
 * @param {boolean} [options.trailingZeros=true]
 * @returns {string}
 */
export function formatFloat(value, options = {}) {
    let precision;
    if (options.digits && options.digits[1] !== undefined) {
        precision = options.digits[1];
    } else if (options.minDigits) {
        precision = 6;
    } else {
        precision = 2;
    }
    const intDigitsCount =
        value !== 0 ? Math.floor(Math.log10(Math.abs(value))) + 1 : 1;
    const maxDecDigits = Math.max(15 - intDigitsCount, 0);
    precision = Math.min(precision, maxDecDigits);
    const minPrecision = Math.min(options.minDigits || precision, precision);
    if (floatIsZero(value, precision)) {
        value = 0.0;
    }
    if (options.humanReadable) {
        return humanNumber(value, options);
    }
    const grouping = options.grouping || l10n.grouping;
    const thousandsSep =
        "thousandsSep" in options ? options.thousandsSep : l10n.thousandsSep;
    const decimalPoint =
        "decimalPoint" in options ? options.decimalPoint : l10n.decimalPoint;
    const fixed = formatFixedDecimals(value, precision);
    if (fixed.includes("e")) {
        return fixed;
    }
    const formatted = fixed.split(".");
    formatted[0] = insertThousandsSep(formatted[0], thousandsSep, grouping);
    if (formatted[1]) {
        formatted[1] = formatted[1].replace(/0+$/, "");
        if (options.trailingZeros !== false) {
            formatted[1] = formatted[1].padEnd(minPrecision, "0");
        }
    }
    return formatted[1] ? formatted.join(decimalPoint) : formatted[0];
}

const _INVERTDICT = Object.freeze({
    1e-1: 1e1,
    1e-2: 1e2,
    1e-3: 1e3,
    1e-4: 1e4,
    1e-5: 1e5,
    1e-6: 1e6,
    1e-7: 1e7,
    1e-8: 1e8,
    1e-9: 1e9,
    1e-10: 1e10,
    2e-1: 5,
    2e-2: 5e1,
    2e-3: 5e2,
    2e-4: 5e3,
    2e-5: 5e4,
    2e-6: 5e5,
    2e-7: 5e6,
    2e-8: 5e7,
    2e-9: 5e8,
    2e-10: 5e9,
    5e-1: 2,
    5e-2: 2e1,
    5e-3: 2e2,
    5e-4: 2e3,
    5e-5: 2e4,
    5e-6: 2e5,
    5e-7: 2e6,
    5e-8: 2e7,
    5e-9: 2e8,
    5e-10: 2e9,
});

/**
 * @param {number} value
 * @returns {number}
 */
function invertFloat(value) {
    let res = /** @type {Record<number, number>} */ (_INVERTDICT)[value];
    if (res === undefined) {
        const [coeff, expt] = value.toExponential().split("e").map(Number.parseFloat);
        res = Number.parseFloat(`${coeff}e${-expt}`) / coeff ** 2;
    }
    return res;
}
