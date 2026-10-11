// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";

const log = makeLogger("web.core.operation");

export class Operation {
    /**
     * @param {"+" | "-" | "*" | "/"} operator
     * @param {number} operand
     * @param {{ integer?: boolean }} [options]
     */
    constructor(operator, operand, { integer = false } = {}) {
        this.operator = operator;
        this.operand = operand;
        this.integer = integer;
    }

    /**
     * @param {number | string | boolean | null | undefined} value
     * @returns {number}
     */
    compute(value) {
        const result = this._apply(Number(value) || 0);
        if (!this.integer || Number.isInteger(result)) {
            return result;
        }
        log.logic("integer operation truncated", () => ({
            operator: this.operator,
            operand: this.operand,
            value,
            result,
        }));
        return Math.trunc(result);
    }

    /**
     * @param {number} current
     * @returns {number}
     */
    _apply(current) {
        switch (this.operator) {
            case "+":
                return current + this.operand;
            case "-":
                return current - this.operand;
            case "*":
                return current * this.operand;
            case "/":
                return current / this.operand;
            default:
                throw new Error(`Unsupported operator: ${this.operator}`);
        }
    }
}
