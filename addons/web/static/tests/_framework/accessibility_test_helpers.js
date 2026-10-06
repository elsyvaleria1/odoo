// @ts-check

import { getFixture } from "@odoo/hoot";

/**
 * @param {Element} [target]
 * @returns {Promise<Record<string, string[]>>}
 */
export async function getAccessibilityViolations(target = getFixture()) {
    const axe = /** @type {any} */ (window).axe;
    const { violations } = await axe.run(target, { resultTypes: ["violations"] });
    return Object.fromEntries(
        violations.map((/** @type {any} */ violation) => [
            violation.id,
            violation.nodes.map((/** @type {any} */ node) => node.target.join(" ")),
        ]),
    );
}
