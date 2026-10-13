/** @odoo-module native */
// @ts-check

/**
 * @param {Array} a
 * @param {Array} b
 * @private
 * @returns {Array}
 */
export function intersect(a, b) {
    return a.filter((x) => b.includes(x));
}

/**
 * @param {Date} value
 * @returns {string}
 */
export function toServerDateString(value) {
    return `${value.getFullYear()}-${value.getMonth() + 1}-${value.getDate()}`;
}

/**
 * @param {number[]} array
 * @returns {number}
 */
export function sum(array) {
    return array.reduce((acc, n) => acc + n, 0);
}

/**
 * @param {string} word
 */
function camelToSnakeKey(word) {
    const result = word.replace(/(.){1}([A-Z])/g, "$1 $2");
    return result.split(" ").join("_").toLowerCase();
}

/**
 * @param {object} obj
 * @returns {object}
 */
export function camelToSnakeObject(obj) {
    const result = {};
    for (const [key, value] of Object.entries(obj)) {
        const isPojo =
            typeof value === "object" && value !== null && value.constructor === Object;
        result[camelToSnakeKey(key)] = isPojo ? camelToSnakeObject(value) : value;
    }
    return result;
}

export function isEmpty(item) {
    if (!item) {
        return true;
    }
    if (typeof item === "object") {
        if (
            Object.values(item).length === 0 ||
            Object.values(item).every((val) => val === undefined)
        ) {
            return true;
        }
    }
    return false;
}

/**
 * @param {import("@odoo/o-spreadsheet").Cell} cell
 */
export function containsReferences(cell) {
    if (!cell.isFormula) {
        return false;
    }
    return cell.compiledFormula.tokens.some((token) => token.type === "REFERENCE");
}
