// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";

import { ASTType } from "./ast_type.js";
import { PyDate, PyDateTime, PyTime } from "./py_date.js";
import { bp } from "./py_parser.js";

/** @typedef {import("./ast_type.js").AST} AST */

const log = makeLogger("web.py");

/**
 * @template T
 * @typedef {T extends null ? import("./ast_type").ASTNone :
 * T extends string | Date | PyDate | PyDateTime | PyTime ? import("./ast_type").ASTString :
 * T extends number ? import("./ast_type").ASTNumber :
 * T extends boolean ? import("./ast_type").ASTBoolean :
 * T extends (infer V)[] ? {type: 4, value: PyValue<V>[]} :
 * T extends object ? {type: 11, value: {[K in keyof T]: PyValue<T[K]>}} : AST} PyValue
 */

/**
 * @template T
 * @overload
 * @param {T} value
 * @returns {PyValue<T>}
 */
/**
 * @param {any} value
 * @returns {AST}
 */
export function toPyValue(value) {
    switch (typeof value) {
        case "string":
            return { type: ASTType.String, value };
        case "number":
            return { type: ASTType.Number, value };
        case "boolean":
            return { type: ASTType.Boolean, value };
        case "object":
            if (Array.isArray(value)) {
                return { type: ASTType.List, value: value.map(toPyValue) };
            } else if (value === null) {
                return { type: ASTType.None };
            } else if (value instanceof Date) {
                return {
                    type: ASTType.String,
                    value: PyDateTime.convertDate(value).strftime("%Y-%m-%d %H:%M:%S"),
                };
            } else if (value instanceof PyDateTime) {
                return {
                    type: ASTType.String,
                    value: value.strftime("%Y-%m-%d %H:%M:%S"),
                };
            } else if (value instanceof PyTime) {
                return { type: ASTType.String, value: value.strftime("%H:%M:%S") };
            } else if (value instanceof PyDate) {
                return { type: ASTType.String, value: value.strftime("%Y-%m-%d") };
            } else {
                /** @type {Record<string, any>} */
                const content = {};
                const order = pyDictKeys(value);
                for (const key of order) {
                    content[key] = toPyValue(value[key]);
                }
                const numberKeys = order.filter((key) => isNumberKey(value, key));
                const keyOrder = keyOrderIfReordered(content, order);
                return {
                    type: ASTType.Dictionary,
                    value: content,
                    ...(numberKeys.length ? { numberKeys } : {}),
                    ...(keyOrder ? { keyOrder } : {}),
                };
            }
        default:
            throw new Error("Invalid type");
    }
}

const COMPARATORS = new Set([
    "in",
    "not in",
    "is",
    "is not",
    "<",
    "<=",
    ">",
    ">=",
    "==",
    "!=",
]);

/**
 * @param {string} str
 * @param {number} abp
 * @param {number} lbp
 * @returns {string}
 */
function parenthesize(str, abp, lbp) {
    return abp < lbp ? `(${str})` : str;
}

/**
 * @param {AST} ast
 * @param {number} lbp
 * @returns {string | null}
 */
function formatOperatorAST(ast, lbp) {
    switch (ast.type) {
        case ASTType.UnaryOperator: {
            const abp = ast.op === "not" ? bp("not") : 130;
            const right = formatAST(ast.right, abp);
            return parenthesize(
                ast.op === "not" ? `not ${right}` : ast.op + right,
                abp,
                lbp,
            );
        }
        case ASTType.BinaryOperator: {
            const abp = bp(ast.op);
            let leftBp = abp;
            let rightBp = abp + 1;
            if (ast.op === "**") {
                leftBp = abp + 1;
                rightBp = abp;
            } else if (COMPARATORS.has(ast.op)) {
                leftBp = abp + 1;
            }
            const left = formatAST(ast.left, leftBp);
            return parenthesize(
                `${left} ${ast.op} ${formatAST(ast.right, rightBp)}`,
                abp,
                lbp,
            );
        }
        case ASTType.BooleanOperator: {
            const abp = bp(ast.op);
            const left = formatAST(ast.left, abp);
            return parenthesize(
                `${left} ${ast.op} ${formatAST(ast.right, abp + 1)}`,
                abp,
                lbp,
            );
        }
        case ASTType.If: {
            const { ifTrue, condition, ifFalse } = ast;
            const abp = bp("if");
            const head = `${formatAST(ifTrue, abp + 1)} if ${formatAST(condition, abp + 1)}`;
            return parenthesize(`${head} else ${formatAST(ifFalse, abp)}`, abp, lbp);
        }
        case ASTType.Chain: {
            const abp = bp(ast.operators[0]);
            const str = ast.operands
                .map((operand, i) =>
                    i === 0
                        ? formatAST(operand, abp + 1)
                        : `${ast.operators[i - 1]} ${formatAST(operand, abp + 1)}`,
                )
                .join(" ");
            return parenthesize(str, abp, lbp);
        }
    }
    return null;
}

/**
 * @param {AST} target
 * @param {"[" | "." | "("} postfix
 * @returns {string}
 */
function formatPostfixTarget(target, postfix) {
    let formatted = formatAST(target, bp(postfix));
    if (
        postfix === "." &&
        target.type === ASTType.Number &&
        !formatted.startsWith("(")
    ) {
        formatted = `(${formatted})`;
    }
    log.logic("postfix target", () => ({
        postfix,
        targetType: target.type,
        parenthesized: formatted !== formatAST(target),
    }));
    return formatted;
}

/**
 * @param {AST} ast
 * @returns {string | null}
 */
function formatCollectionAST(ast) {
    switch (ast.type) {
        case ASTType.List:
            return `[${ast.value.map((v) => formatAST(v)).join(", ")}]`;
        case ASTType.Tuple: {
            const items = ast.value.map((v) => formatAST(v));
            return items.length === 1 ? `(${items[0]},)` : `(${items.join(", ")})`;
        }
        case ASTType.Dictionary: {
            const numberKeys = new Set(ast.numberKeys);
            log.logic("format dict", () => ({
                keyOrder: ast.keyOrder?.join(",") ?? null,
            }));
            const pairs = (ast.keyOrder ?? Object.keys(ast.value || {})).map(
                (k) =>
                    `${numberKeys.has(k) ? k : JSON.stringify(k)}: ${formatAST(ast.value[k])}`,
            );
            return `{${pairs.join(", ")}}`;
        }
        case ASTType.Lookup:
            return `${formatPostfixTarget(ast.target, "[")}[${formatAST(ast.key)}]`;
        case ASTType.ObjLookup:
            return `${formatPostfixTarget(ast.obj, ".")}.${ast.key}`;
        case ASTType.FunctionCall: {
            const args = ast.args.map((v) => formatAST(v));
            const kwargs = Object.keys(ast.kwargs || {}).map(
                (kwarg) => `${kwarg} = ${formatAST(ast.kwargs[kwarg])}`,
            );
            return `${formatPostfixTarget(ast.fn, "(")}(${[...args, ...kwargs].join(", ")})`;
        }
    }
    return null;
}

/**
 * @param {AST} ast
 * @param {number} [lbp]
 * @return {string}
 */
export function formatAST(ast, lbp = 0) {
    switch (ast.type) {
        case ASTType.None:
            return "None";
        case ASTType.String:
            return JSON.stringify(ast.value);
        case ASTType.Number: {
            const str = String(ast.value);
            return ast.value < 0 && lbp >= 130 ? `(${str})` : str;
        }
        case ASTType.Boolean:
            return ast.value ? "True" : "False";
        case ASTType.Name:
            return ast.value;
    }
    const formatted = formatOperatorAST(ast, lbp) ?? formatCollectionAST(ast);
    if (formatted === null) {
        throw new Error(`invalid expression: ${ast}`);
    }
    return formatted;
}

/**
 * @param {any} value
 * @returns {boolean}
 */
export function isPyMapping(value) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
        return false;
    }
    const proto = Object.getPrototypeOf(value);
    return proto === Object.prototype || proto === null;
}

/** @type {WeakMap<object, Set<string>>} */
const NUMBER_KEYS = new WeakMap();

/**
 * @template {object} T
 * @param {T} dict
 * @param {Iterable<string>} keys
 * @returns {T}
 */
export function markNumberKeys(dict, keys) {
    const set = new Set(keys);
    if (set.size) {
        NUMBER_KEYS.set(dict, set);
    }
    return dict;
}

/**
 * @param {object} dict
 * @param {string} key
 * @returns {boolean}
 */
export function isNumberKey(dict, key) {
    return NUMBER_KEYS.get(dict)?.has(key) ?? false;
}

/** @type {WeakMap<object, string[]>} */
const KEY_ORDER = new WeakMap();

/**
 * @param {Record<string, any>} dict
 * @param {string[]} order
 * @returns {string[] | null}
 */
export function keyOrderIfReordered(dict, order) {
    const keys = Object.keys(dict);
    return order.length === keys.length && order.every((k, i) => k === keys[i])
        ? null
        : order;
}

/**
 * JS enumerates integer-like keys ("9", "10") before the others, so a dict
 * holding one keeps its insertion order here for repr and iteration.
 *
 * @template {object} T
 * @param {T} dict
 * @param {string[]} order
 * @returns {T}
 */
export function markKeyOrder(dict, order) {
    const reordered = keyOrderIfReordered(dict, order);
    log.logic("dict key order", () => ({
        order: order.join(","),
        tracked: reordered !== null,
    }));
    if (reordered) {
        KEY_ORDER.set(dict, reordered);
    }
    return dict;
}

/**
 * @param {object} dict
 * @returns {string[]}
 */
export function pyDictKeys(dict) {
    return KEY_ORDER.get(dict) ?? Object.keys(dict);
}
