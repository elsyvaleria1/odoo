// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import { parseDate, parseDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { ParseError } from "@web/core/parse_error";
import { evaluateExpr } from "@web/core/py_js/py";
import { registry } from "@web/core/registry";
import { Operation } from "@web/core/utils/operation";

/**
 * @param {(key: string) => RegExp} build
 * @returns {(key: string) => RegExp}
 */
function memoizeRegex(build) {
    /** @type {Map<string, RegExp>} */
    const cache = new Map();
    return (key) => {
        let regex = cache.get(key);
        if (!regex) {
            regex = build(key);
            cache.set(key, regex);
        }
        return regex;
    };
}

const log = makeLogger("web.core.parsers");

const getOperationRegex = memoizeRegex(
    (decimalPoint) =>
        new RegExp(
            `^(?<operator>[+\\-*/])\\s*=\\s*(?<operand>-?\\d+(?:[${RegExp.escape(
                decimalPoint,
            )}]\\d+)?)$`,
        ),
);
const getThousandsSepRegex = memoizeRegex(
    (thousandsSep) => new RegExp(RegExp.escape(thousandsSep)),
);
const getDecimalMarkerRegex = memoizeRegex(
    (markers) => new RegExp(`[${RegExp.escape(markers)}]`),
);
const getMonetaryStartRegex = memoizeRegex(
    (decimalPoint) => new RegExp(`[\\d\\-+=]|${RegExp.escape(decimalPoint)}`),
);

const WHITESPACE_THOUSANDS_SEP_REGEX = /\s+/;
const SIGN_REGEX = /^[+-]?/;
const DIGITS_REGEX = /^\d+$/;

const DECIMAL_LITERAL_REGEX = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

const PARENTHESISED_NEGATIVE_REGEX = /^(\D*)\((.*)\)(\D*)$/;
const TRAILING_MINUS_REGEX = /-\s*$/;

const EXPRESSION_TOKEN_REGEX = /([*/()^]|(?<![\d.,][eE])[-+])/;
const EXPRESSION_OPERATORS = ["+", "-", "*", "/", "(", ")", "^"];

function evaluateMathematicalExpression(/** @type {string} */ expr) {
    const val = expr.replaceAll(" ", "");
    let safeEvalString = "";
    for (const part of val.split(EXPRESSION_TOKEN_REGEX)) {
        /** @type {any} */
        let v = part;
        if (!EXPRESSION_OPERATORS.includes(v) && v.length) {
            v = parseFloat(v);
        }
        if (v === "^") {
            v = "**";
        }
        safeEvalString += v;
    }
    return evaluateExpr(safeEvalString);
}

/**
 * @param {string} value
 * @param {(v: string) => any} parseValueFn
 * @param {{ integer?: boolean }} [options]
 * @returns {import("@web/core/utils/operation").Operation | false}
 * @throws {InvalidNumberError}
 */
function parseOperation(value, parseValueFn, { integer = false } = {}) {
    const match = value.trim().match(getOperationRegex(localization.decimalPoint));
    if (match?.groups) {
        const operand = parseValueFn(match.groups.operand);
        const operator = match.groups.operator;
        if (operator === "/" && operand === 0) {
            log.logic("operation divides by zero", () => ({ value, integer }));
            throw new InvalidNumberError(`"${value}" divides by zero`);
        }
        return new Operation(/** @type {any} */ (operator), operand, { integer });
    }
    return false;
}

/**
 * @param {number[]} grouping
 * @param {number} count
 * @returns {number[]}
 */
function groupSizes(grouping, count) {
    /** @type {number[]} */
    const sizes = [];
    let index = 0;
    while (sizes.length < count) {
        const section = grouping[index];
        if (section === undefined || section === -1 || (section === 0 && index === 0)) {
            break;
        }
        if (section === 0) {
            sizes.push(sizes[sizes.length - 1]);
        } else {
            sizes.push(section);
            index++;
        }
    }
    return sizes;
}

/**
 * @param {string[]} groups
 * @param {number[]} grouping
 * @returns {boolean}
 */
function isGroupedAtBoundaries(groups, grouping) {
    const trailing = groups.length - 1;
    const sizes = groupSizes(grouping, groups.length);
    if (sizes.length < trailing || !groups.every((group) => DIGITS_REGEX.test(group))) {
        return false;
    }
    for (let k = 0; k < trailing; k++) {
        if (groups[trailing - k].length !== sizes[k]) {
            return false;
        }
    }
    const leadingSize = sizes[trailing];
    return leadingSize === undefined || groups[0].length <= leadingSize;
}

/**
 * @param {string} value
 * @param {{ thousandsSep: string | false, decimalPoint: string, grouping: number[] }} options
 * @returns {number}
 */
function parseNumber(value, options) {
    value = value.trim();
    if (value.startsWith("=")) {
        try {
            return Number(evaluateMathematicalExpression(value.slice(1)));
        } catch (error) {
            if (error instanceof InvalidNumberError) {
                throw error;
            }
            throw new InvalidNumberError(`"${value}" is not a valid expression`, {
                cause: error,
            });
        }
    }
    const { thousandsSep, decimalPoint, grouping } = options;
    const decimalMarkers =
        thousandsSep === "." || decimalPoint === "."
            ? decimalPoint
            : `${decimalPoint}.`;
    const parts = value.split(getDecimalMarkerRegex(decimalMarkers));
    if (parts.length > 2) {
        return NaN;
    }
    const sign = parts[0].match(SIGN_REGEX)?.[0] ?? "";
    let integerPart = parts[0].slice(sign.length);
    if (thousandsSep) {
        const groups = integerPart.split(
            /\s/.test(thousandsSep)
                ? WHITESPACE_THOUSANDS_SEP_REGEX
                : getThousandsSepRegex(thousandsSep),
        );
        if (groups.length > 1) {
            const grouped = isGroupedAtBoundaries(groups, grouping);
            log.logic("thousands separators", () => ({
                value,
                thousandsSep,
                grouping,
                groups,
                grouped,
            }));
            if (!grouped) {
                return NaN;
            }
            integerPart = groups.join("");
        }
    }
    const literal =
        parts.length === 2 ? `${sign}${integerPart}.${parts[1]}` : sign + integerPart;
    return DECIMAL_LITERAL_REGEX.test(literal) ? Number(literal) : NaN;
}

export class InvalidNumberError extends ParseError {}

const ENGLISH_NUMBER_CONVENTION = Object.freeze({
    thousandsSep: ",",
    decimalPoint: ".",
    grouping: [3, 0],
});

/**
 * @param {string} value
 * @returns {number}
 * @throws {InvalidNumberError}
 */
function parseInLocale(value) {
    let parsed = parseNumber(value, {
        thousandsSep: localization.thousandsSep,
        decimalPoint: localization.decimalPoint,
        grouping: localization.grouping,
    });
    if (Number.isNaN(parsed)) {
        parsed = parseNumber(value, ENGLISH_NUMBER_CONVENTION);
        if (Number.isNaN(parsed)) {
            throw new InvalidNumberError(`"${value}" is not a correct number`);
        }
    }
    if (!Number.isFinite(parsed)) {
        throw new InvalidNumberError(`"${value}" is not a valid number`);
    }
    return parsed;
}

/**
 * @param {string} value
 * @param {{ allowOperation?: boolean }} [options]
 * @returns {number}
 */
export function parseFloat(value, { allowOperation = false } = {}) {
    if (typeof value === "string" && value.trim() === "") {
        return 0;
    }
    const operation = allowOperation ? parseOperation(value, parseFloat) : null;
    if (operation instanceof Operation) {
        // @ts-expect-error returns Operation when allowOperation is true
        return operation;
    }
    return parseInLocale(value);
}

/**
 * @param {string} value
 * @returns {number}
 */
export function parseFloatTime(value) {
    value = value.trim();
    let sign = 1;
    if (value[0] === "-") {
        value = value.slice(1);
        sign = -1;
    }
    const values = value.split(":");
    if (values.length > 3) {
        throw new InvalidNumberError(`"${value}" is not a correct number`);
    }
    if (values.length === 1) {
        return sign * parseFloat(value);
    }
    const hours = parseInteger(values[0]);
    const minutes = parseInteger(values[1]);
    if (minutes < 0 || minutes >= 60) {
        throw new InvalidNumberError(`"${value}" is not a correct number`);
    }
    let seconds = 0;
    if (values.length === 3) {
        seconds = parseInteger(values[2]);
        if (seconds < 0 || seconds >= 60) {
            throw new InvalidNumberError(`"${value}" is not a correct number`);
        }
    }
    return sign * (hours + minutes / 60 + seconds / 3600);
}

/**
 * @param {string} value
 * @param {{ allowOperation?: boolean }} [options]
 * @returns {number}
 */
export function parseInteger(value, { allowOperation = false } = {}) {
    if (typeof value === "string" && value.trim() === "") {
        return 0;
    }
    const operation = allowOperation
        ? parseOperation(value, parseInteger, { integer: true })
        : null;
    if (operation instanceof Operation) {
        // @ts-expect-error returns Operation when allowOperation is true
        return operation;
    }
    const parsed = parseInLocale(value);
    if (!Number.isInteger(parsed)) {
        throw new InvalidNumberError(`"${value}" is not a correct number`);
    }
    assertInt32(value, parsed);
    return parsed;
}

/**
 * @param {string} value
 * @param {number} parsed
 * @throws {InvalidNumberError}
 */
export function assertInt32(value, parsed) {
    if (parsed < -2147483648 || parsed > 2147483647) {
        throw new InvalidNumberError(
            `"${value}" is out of bounds (integers should be between -2,147,483,648 and 2,147,483,647)`,
        );
    }
}

/**
 * @param {string} value
 * @param {{ allowOperation?: boolean }} [options]
 * @returns {number | import("@web/core/utils/operation").Operation}
 */
export function parsePercentage(value, { allowOperation = false } = {}) {
    value = value.trim();
    if (value.at(-1) === "%") {
        value = value.slice(0, -1);
    }
    const parsed = /** @type {number | Operation} */ (
        parseFloat(value, { allowOperation })
    );
    if (parsed instanceof Operation) {
        return parsed;
    }
    return parsed / 100;
}

/**
 * @param {string} value
 * @param {{ allowOperation?: boolean }} [options]
 * @returns {number}
 */
export function parseMonetary(value, { allowOperation = false } = {}) {
    const operation = allowOperation ? parseOperation(value, parseMonetary) : null;
    if (operation instanceof Operation) {
        // @ts-expect-error returns Operation when allowOperation is true
        return operation;
    }
    value = value.trim();
    const startRegex = getMonetaryStartRegex(localization.decimalPoint);

    const expressionMatch = value.match(startRegex);
    const body = expressionMatch ? value.slice(expressionMatch.index) : value;
    if (body.startsWith("=")) {
        return parseFloat(body);
    }

    let sign = 1;
    const parenthesised = value.match(PARENTHESISED_NEGATIVE_REGEX);
    if (parenthesised) {
        sign = -sign;
        value = `${parenthesised[1]}${parenthesised[2]}${parenthesised[3]}`;
    }
    if (/\d/.test(value) && TRAILING_MINUS_REGEX.test(value)) {
        sign = -sign;
        value = value.replace(TRAILING_MINUS_REGEX, "");
    }

    const startMatch = value.match(startRegex);
    if (startMatch) {
        value = value.slice(startMatch.index);
    }
    if (value[0] === "-" || value[0] === "+") {
        const leadingSign = value[0];
        const rest = value.slice(1);
        const restMatch = rest.match(startRegex);
        value = leadingSign + (restMatch ? rest.slice(restMatch.index) : rest);
    }
    value = value.replace(/\D*$/, "");
    return sign * parseFloat(value);
}

registry
    .category("parsers")
    .add("date", parseDate)
    .add("datetime", parseDateTime)
    .add("float", parseFloat)
    .add("float_time", parseFloatTime)
    .add("integer", parseInteger)
    .add("many2one_reference", parseInteger)
    .add("monetary", parseMonetary)
    .add("percentage", parsePercentage);

registry.category("parsers").addValidation((v) => typeof v === "function");
