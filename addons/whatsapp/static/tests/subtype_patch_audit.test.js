// @ts-check
import { getShadowedPatches } from "@mail/../tests/patch_audit";
import { describe, expect, test } from "@odoo/hoot";

describe.current.tags("headless");

test("no patch of a parent model is silently shadowed by a subtype", () => {
    expect(getShadowedPatches()).toEqual([], {
        message:
            "these parent patches never run for subtype records; move the patch to the subtype" +
            " or call super from the subtype",
    });
});
