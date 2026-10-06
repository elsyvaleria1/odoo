// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";

import {
    NotSupportedError,
    PyDate,
    PyDateTime,
    PyRelativeDelta,
    PyTime,
} from "./py_date.js";
import { EvaluationError } from "./py_errors.js";
import { PyTimeDelta } from "./py_timedelta.js";
import { isPyTuple } from "./py_tuple.js";
import { pyTypeName } from "./py_type_name.js";

const log = makeLogger("web.py");

export class UnorderableError extends NotSupportedError {
    /**
     * @param {any} left
     * @param {any} right
     */
    constructor(left, right) {
        super(
            `not supported between instances of '${pyTypeName(left)}' and '${pyTypeName(right)}'`,
        );
        this.left = left;
        this.right = right;
    }

    /**
     * @param {string} op
     * @param {boolean} swapped
     * @returns {NotSupportedError}
     */
    withOperator(op, swapped) {
        const [left, right] = swapped
            ? [this.right, this.left]
            : [this.left, this.right];
        return new NotSupportedError(
            `'${op}' not supported between instances of '${pyTypeName(left)}' and '${pyTypeName(right)}'`,
        );
    }
}

/**
 * @param {any} value
 * @returns {"date" | "datetime" | "time" | "timedelta" | null}
 */
function pyTemporalKind(value) {
    if (value instanceof PyTime) {
        return "time";
    }
    if (value instanceof PyDate) {
        return "date";
    }
    if (value instanceof PyDateTime) {
        return "datetime";
    }
    if (value instanceof PyTimeDelta) {
        return "timedelta";
    }
    return null;
}

/**
 * @param {any} value
 * @returns {boolean}
 */
function isNumeric(value) {
    return typeof value === "number" || typeof value === "boolean";
}

const SURROGATE = /[\ud800-\udfff]/;

/**
 * @param {string} left
 * @param {string} right
 * @returns {boolean}
 */
function isLessString(left, right) {
    if (!SURROGATE.test(left) && !SURROGATE.test(right)) {
        return left < right;
    }
    const a = [...left];
    const b = [...right];
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) {
        const diff =
            /** @type {number} */ (a[i].codePointAt(0)) -
            /** @type {number} */ (b[i].codePointAt(0));
        if (diff) {
            return diff < 0;
        }
    }
    return a.length < b.length;
}

/**
 * @param {any[]} left
 * @param {any[]} right
 * @returns {boolean}
 */
function isLessSequence(left, right) {
    const n = Math.min(left.length, right.length);
    for (let i = 0; i < n; i++) {
        if (!isEqual(left[i], right[i])) {
            return isLess(left[i], right[i]);
        }
    }
    return left.length < right.length;
}

/**
 * @param {Set<any>} subset
 * @param {Set<any>} superset
 * @returns {boolean}
 */
function coversSet(subset, superset) {
    const unmatched = new Set(superset);
    for (const value of subset) {
        if (unmatched.delete(value)) {
            continue;
        }
        let matched = false;
        for (const candidate of unmatched) {
            if (isEqual(value, candidate)) {
                unmatched.delete(candidate);
                matched = true;
                break;
            }
        }
        if (!matched) {
            return false;
        }
    }
    return true;
}

/**
 * CPython's ordering: numbers (bool included) against numbers, str against str,
 * a list or a tuple against its own kind, a set against a set, a temporal value
 * against its own kind; any other pair raises TypeError. One pair stays lax:
 * a bool against a str, because the client hands an unset date, char or
 * selection field to an expression as False, and views compare such fields
 * against date strings (`date_deadline < current_date`); False orders first.
 *
 * @param {any} left
 * @param {any} right
 * @returns {boolean}
 */
export function isLess(left, right) {
    if (isNumeric(left) && isNumeric(right)) {
        return Number(left) < Number(right);
    }
    if (typeof left === "string" && typeof right === "string") {
        return isLessString(left, right);
    }
    if (left instanceof Set && right instanceof Set) {
        return left.size < right.size && coversSet(left, right);
    }
    if (
        Array.isArray(left) &&
        Array.isArray(right) &&
        isPyTuple(left) === isPyTuple(right)
    ) {
        return isLessSequence(left, right);
    }
    const temporalKind = pyTemporalKind(left);
    if (temporalKind && temporalKind === pyTemporalKind(right)) {
        return left < right;
    }
    const unsetAgainstString =
        (typeof left === "boolean" && typeof right === "string") ||
        (typeof left === "string" && typeof right === "boolean");
    log.logic("unorderable pair", () => ({
        left: pyTypeName(left),
        right: pyTypeName(right),
        result: unsetAgainstString ? "bool orders before str" : "TypeError",
    }));
    if (unsetAgainstString) {
        return typeof left === "boolean";
    }
    throw new UnorderableError(left, right);
}

/**
 * @param {any} left
 * @param {any} right
 * @returns {boolean}
 */
export function isEqual(left, right) {
    if (typeof left !== typeof right) {
        if (typeof left === "boolean" && typeof right === "number") {
            return right === (left ? 1 : 0);
        }
        if (typeof left === "number" && typeof right === "boolean") {
            return left === (right ? 1 : 0);
        }
        return false;
    }
    if (left instanceof Object && typeof left.isEqual === "function") {
        return left.isEqual(right);
    }
    if (Array.isArray(left) || Array.isArray(right)) {
        if (!Array.isArray(left) || !Array.isArray(right)) {
            return false;
        }
        if (isPyTuple(left) !== isPyTuple(right)) {
            return false;
        }
        return (
            left.length === right.length && left.every((v, i) => isEqual(v, right[i]))
        );
    }
    if (left instanceof Set || right instanceof Set) {
        if (
            !(left instanceof Set) ||
            !(right instanceof Set) ||
            left.size !== right.size
        ) {
            return false;
        }
        return coversSet(left, right);
    }
    if (
        left !== null &&
        right !== null &&
        typeof left === "object" &&
        typeof right === "object"
    ) {
        if (typeof left.isEqual === "function" || typeof right.isEqual === "function") {
            return false;
        }
        const leftKeys = Object.keys(left);
        const rightKeys = Object.keys(right);
        if (leftKeys.length !== rightKeys.length) {
            return false;
        }
        return leftKeys.every(
            (k) => Object.hasOwn(right, k) && isEqual(left[k], right[k]),
        );
    }
    return left === right;
}

/**
 * @param {any} value
 * @returns {string | null}
 */
function unhashableTypeName(value) {
    if (value instanceof Set || (Array.isArray(value) && !isPyTuple(value))) {
        return pyTypeName(value);
    }
    if (Array.isArray(value)) {
        for (const item of value) {
            const inner = unhashableTypeName(item);
            if (inner) {
                return inner;
            }
        }
        return null;
    }
    if (value !== null && typeof value === "object" && pyTemporalKind(value) === null) {
        return value instanceof PyRelativeDelta ? null : pyTypeName(value);
    }
    return null;
}

/**
 * @param {any} key
 * @param {"a dict key" | "a set element"} role
 */
export function assertHashable(key, role) {
    const unhashable = unhashableTypeName(key);
    if (unhashable) {
        log.logic("unhashable key", () => ({ role, key: pyTypeName(key), unhashable }));
        throw new EvaluationError(
            `TypeError: cannot use '${pyTypeName(key)}' as ${role} (unhashable type: '${unhashable}')`,
        );
    }
}

/**
 * The property a hashable key reads on a dict: bool is int, so True reads 1.
 *
 * @param {any} key
 * @returns {any}
 */
export function dictLookupKey(key) {
    assertHashable(key, "a dict key");
    return typeof key === "boolean" ? Number(key) : key;
}

/**
 * CPython's `in`: a str right operand wants a str left one, a container
 * compares or hashes, anything else raises TypeError. False (and a field the
 * record did not load, undefined) stays lax on either side of a str and on the
 * right of any value: the client hands an unset char or selection field to an
 * expression as False, and views test such fields against a literal
 * (`state in 'draft'`, `'UZ' in fiscal_country_codes`).
 *
 * @param {any} left
 * @param {any} right
 * @returns {boolean}
 */
export function isIn(left, right) {
    if (Array.isArray(right)) {
        return right.some((x) => isEqual(left, x));
    }
    if (typeof right === "string") {
        if (typeof left === "string") {
            return right.includes(left);
        }
        const unset = left === false || left === undefined;
        log.logic("in: non-str left of a str", () => ({
            left: left === undefined ? "undefined" : pyTypeName(left),
            result: unset ? "False (unset field)" : "TypeError",
        }));
        if (unset) {
            return false;
        }
        throw new EvaluationError(
            `TypeError: 'in <string>' requires string as left operand, not ${pyTypeName(left)}`,
        );
    }
    if (right instanceof Set) {
        assertHashable(left, "a set element");
        for (const x of right) {
            if (isEqual(left, x)) {
                return true;
            }
        }
        return false;
    }
    if (
        right !== null &&
        typeof right === "object" &&
        pyTemporalKind(right) === null &&
        !(right instanceof PyRelativeDelta)
    ) {
        return Object.hasOwn(right, dictLookupKey(left));
    }
    const unset = right === false || right === undefined;
    log.logic("in: non-container right", () => ({
        right: right === undefined ? "undefined" : pyTypeName(right),
        result: unset ? "False (unset field)" : "TypeError",
    }));
    if (unset) {
        return false;
    }
    throw new EvaluationError(
        `TypeError: argument of type '${pyTypeName(right)}' is not a container or iterable`,
    );
}
