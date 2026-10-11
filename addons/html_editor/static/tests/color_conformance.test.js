/** @odoo-module native */
/**
 * JS half of the color grammar conformance suite; the Python half is
 * `html_editor/tests/test_color_conformance.py`. Add a case to
 * `color_conformance_vectors.js`, not here.
 */

import { VECTORS as vectors } from "@html_editor/../tests/color_conformance_vectors";
import { expect, test } from "@odoo/hoot";
import { parseCSSColor } from "@web/core/utils/format/colors";

test.tags("headless");
test("conformance: color vectors", () => {
    for (const { value, rgba } of vectors) {
        const parsed = parseCSSColor(value);
        expect(
            parsed && [parsed.red, parsed.green, parsed.blue, parsed.opacity],
        ).toEqual(rgba || false, {
            message: `parseCSSColor(${JSON.stringify(value)})`,
        });
    }
});
