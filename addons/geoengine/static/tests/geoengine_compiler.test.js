import { WITHHELD_DIRECTIVES } from "@geoengine/geoengine/geoengine_record";
import { describe, expect, test } from "@odoo/hoot";
import { RECORD_TEMPLATE_DIRECTIVES } from "@web/views/view_compiler";

/**
 * geoengine's arch-template whitelist is `RECORD_TEMPLATE_DIRECTIVES` minus
 * three. It used to be a fourth hand-written copy of that list, which is why
 * nobody could tell the omission from an independent choice: four separate
 * arrays look the same whether they agree by intent or by accident.
 *
 * These pin the subtraction from both ends. The whitelist gates what a
 * `<geoengine>` arch may CONTAIN, so widening it is a behaviour change, and
 * `RECORD_TEMPLATE_DIRECTIVES` growing upstream must not widen it silently.
 */
describe("geoengine arch-template directives", () => {
    test("the effective whitelist is exactly the ten it has always been", () => {
        const effective = RECORD_TEMPLATE_DIRECTIVES.filter(
            (d) => !WITHHELD_DIRECTIVES.includes(d),
        );
        expect([...effective].sort()).toEqual(
            [
                "t-as",
                "t-att.*",
                "t-elif",
                "t-else",
                "t-esc",
                "t-foreach",
                "t-if",
                "t-key",
                "t-name",
                "t-out",
            ].sort(),
        );
    });

    test("every withheld directive is one the shared list actually offers", () => {
        // A withheld name that no longer appears upstream would subtract
        // nothing, and the divergence would quietly disappear rather than being
        // decided -- the same silence the four copies produced.
        for (const directive of WITHHELD_DIRECTIVES) {
            expect(RECORD_TEMPLATE_DIRECTIVES).toInclude(directive);
        }
    });
});
