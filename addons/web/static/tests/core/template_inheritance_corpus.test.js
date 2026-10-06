// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { CASES } from "@web/../tests/core/template_inheritance_cases";
import { applyInheritance } from "@web/core/template_inheritance";

describe.current.tags("headless");

const parser = new DOMParser();
const serializer = new XMLSerializer();

/** @param {Element} root */
function withoutTranslationContexts(root) {
    for (const element of [root, ...root.querySelectorAll("*")]) {
        for (const { name } of [...element.attributes]) {
            if (name.startsWith("t-translation-context")) {
                element.removeAttribute(name);
            }
        }
    }
    return root;
}

/**
 * @param {{ arch: string, specs: string, error?: string }} testCase
 * @returns {{ result: string } | { error: string }}
 */
function outcome(testCase) {
    const arch = parser.parseFromString(testCase.arch, "text/xml").documentElement;
    const specs = parser.parseFromString(testCase.specs, "text/xml").documentElement;
    try {
        const result = applyInheritance(arch, specs);
        return {
            result: serializer.serializeToString(withoutTranslationContexts(result)),
        };
    } catch (error) {
        const message = String(/** @type {Error} */ (error).message);
        const expected = testCase.error;
        return { error: expected && message.includes(expected) ? expected : message };
    }
}

test("the corpus is not empty", () => {
    expect(CASES.length).toBeGreaterThan(50);
});

for (const testCase of CASES) {
    test(testCase.name, () => {
        expect(outcome(testCase)).toEqual(
            "error" in testCase
                ? { error: testCase.error }
                : { result: testCase.result },
        );
    });
}
