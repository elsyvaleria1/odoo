// @ts-check

import { after, afterEach, describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { applyBootBodyClasses, applyUserTimezone } from "@web/boot/start";
import { browser } from "@web/core/browser/browser";
import { dateSettings } from "@web/core/l10n/date_settings";
import { localization } from "@web/core/l10n/localization";
import { user } from "@web/core/user";

describe.current.tags("headless");

const BOOT_CLASSES = ["o_rtl", "o_is_superuser", "o_touch_device", "o_debug"];

afterEach(() => document.body.classList.remove(...BOOT_CLASSES));

/** @param {{ direction?: "ltr" | "rtl", userId?: number, touch?: boolean }} world */
function given({ direction, userId = 2, touch = false }) {
    if (direction !== undefined) {
        patchWithCleanup(localization, { direction });
    }
    patchWithCleanup(user, { userId });
    patchWithCleanup(browser, {
        ontouchstart: touch ? () => {} : undefined,
        matchMedia: () => /** @type {any} */ ({ matches: false }),
    });
}

describe("applyBootBodyClasses", () => {
    test("adds o_rtl only for an rtl localization", () => {
        given({ direction: "rtl" });
        applyBootBodyClasses();
        expect(document.body).toHaveClass("o_rtl");
    });

    test("adds nothing for an ltr localization", () => {
        given({ direction: "ltr" });
        applyBootBodyClasses();
        expect(document.body).not.toHaveClass("o_rtl");
    });

    test("does not throw when the localization service never started", () => {
        given({});
        expect(() => applyBootBodyClasses()).not.toThrow();
        expect(document.body).not.toHaveClass("o_rtl");
    });

    test("adds o_is_superuser for uid 1 only", () => {
        given({ direction: "ltr", userId: 1 });
        applyBootBodyClasses();
        expect(document.body).toHaveClass("o_is_superuser");
    });

    test("does not add o_is_superuser for the admin user (uid 2)", () => {
        given({ direction: "ltr", userId: 2 });
        applyBootBodyClasses();
        expect(document.body).not.toHaveClass("o_is_superuser");
    });

    test("leaves o_touch_device to the input modality, even on a touch device", () => {
        given({ direction: "ltr", touch: true });
        applyBootBodyClasses();
        expect(document.body).not.toHaveClass("o_touch_device");
    });

    test("never adds o_debug — it has no reader anywhere", () => {
        given({ direction: "rtl", userId: 1, touch: true });
        applyBootBodyClasses();
        expect(document.body).not.toHaveClass("o_debug");
    });
});

describe("applyUserTimezone", () => {
    /** @param {string | undefined} tz */
    function withTz(tz) {
        const before = dateSettings.timeZone;
        after(() => (dateSettings.timeZone = before));
        patchWithCleanup(user, { tz });
    }

    test("applies a valid IANA zone", () => {
        withTz("America/Mexico_City");
        expect(applyUserTimezone()).toBe(true);
        expect(dateSettings.timeZone).toBe("America/Mexico_City");
    });

    test("refuses an unknown zone rather than invalidating every date", () => {
        withTz("Mars/Olympus_Mons");
        const before = dateSettings.timeZone;
        expect(applyUserTimezone()).toBe(false);
        expect(dateSettings.timeZone).toBe(before);
    });

    test("does nothing when the user has no timezone", () => {
        withTz(undefined);
        expect(applyUserTimezone()).toBe(false);
    });
});
