// @ts-check

import { after, describe, expect, test } from "@odoo/hoot";
import {
    MOUNT_ANCHOR_ID,
    startPublicReadonlySpreadsheet,
} from "@spreadsheet/public_readonly_app/boot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { session } from "@web/session";

describe.current.tags("headless");

function restoreGlobals() {
    const info = /** @type {any} */ (odoo).info;
    const ready = /** @type {any} */ (odoo).isReady;
    after(() => {
        /** @type {any} */ (odoo).info = info;
        /** @type {any} */ (odoo).isReady = ready;
        document.getElementById(MOUNT_ANCHOR_ID)?.remove();
    });
}

describe("startPublicReadonlySpreadsheet", () => {
    test("names the anchor it could not find", async () => {
        restoreGlobals();
        patchWithCleanup(session, { spreadsheet_public_props: {} });
        expect(document.getElementById(MOUNT_ANCHOR_ID)).toBe(null);

        await expect(startPublicReadonlySpreadsheet()).rejects.toThrow(
            new RegExp(`no #${MOUNT_ANCHOR_ID} element to mount on`),
        );
    });

    test("publishes odoo.info before it can fail on a missing anchor", async () => {
        restoreGlobals();
        patchWithCleanup(session, {
            db: "publicdb",
            server_version: "19.0+e",
            server_version_info: [19, 0, 0, "final", 0, "e"],
            spreadsheet_public_props: {},
        });
        /** @type {any} */ (odoo).info = undefined;

        await startPublicReadonlySpreadsheet().catch(() => {});

        const info = /** @type {any} */ (odoo).info;
        expect(info?.db).toBe("publicdb");
        expect(info?.isEnterprise).toBe(true);
    });

    test("clears odoo.isReady on entry and does not set it on failure", async () => {
        restoreGlobals();
        patchWithCleanup(session, { spreadsheet_public_props: {} });
        /** @type {any} */ (odoo).isReady = true;

        await startPublicReadonlySpreadsheet().catch(() => {});

        expect(odoo.isReady).toBe(false);
    });
});
