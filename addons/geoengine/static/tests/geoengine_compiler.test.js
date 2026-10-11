import { WITHHELD_DIRECTIVES } from "@geoengine/geoengine/geoengine_record";
import { describe, expect, test } from "@odoo/hoot";
import { RECORD_TEMPLATE_DIRECTIVES } from "@web/views/view_compiler";

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
        for (const directive of WITHHELD_DIRECTIVES) {
            expect(RECORD_TEMPLATE_DIRECTIVES).toInclude(directive);
        }
    });
});
