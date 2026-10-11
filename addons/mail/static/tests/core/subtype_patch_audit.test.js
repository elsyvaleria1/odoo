// @ts-check
import { getShadowedPatches } from "@mail/../tests/patch_audit";
import { describe, expect, test } from "@odoo/hoot";
import { registry } from "@web/core/registry";

describe.current.tags("headless");

const KNOWN_SHADOWED_PATCHES = new Set([]);

test("no patch of a parent model is silently shadowed by a subtype", () => {
    const unknown = getShadowedPatches().filter(
        (entry) => !KNOWN_SHADOWED_PATCHES.has(entry),
    );
    expect(unknown).toEqual([], {
        message:
            "these parent patches never run for subtype records; move the patch to the subtype," +
            " call super from the subtype, or allowlist it in KNOWN_SHADOWED_PATCHES" +
            " (subtype_patch_audit.test.js)",
    });
});

test("the audit sees the thread subtypes", () => {
    const Models = new Set(registry.category("discuss.model").getAll());
    const subtypes = [...Models].filter((Model) => {
        const Parent = Object.getPrototypeOf(Model);
        return Models.has(Parent) && Parent._discriminator;
    });
    expect(subtypes.map((Model) => Model.getName())).toInclude("discuss.channel");
});
