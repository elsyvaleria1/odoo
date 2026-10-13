// @ts-check
/** @odoo-module native */

import { whenReady } from "@odoo/owl";
import { publishOdooInfo } from "@web/core/odoo_info";
import { mountComponent } from "@web/env";
import { session } from "@web/session";

import { PublicReadonlySpreadsheet } from "./public_readonly.js";

export const MOUNT_ANCHOR_ID = "spreadsheet-mount-anchor";

/** @returns {Promise<import("@odoo/owl").App>} */
export async function startPublicReadonlySpreadsheet() {
    publishOdooInfo();
    odoo.isReady = false;
    await whenReady();

    const target = document.getElementById(MOUNT_ANCHOR_ID);
    if (!target) {
        throw new Error(
            `public spreadsheet: no #${MOUNT_ANCHOR_ID} element to mount on`,
        );
    }

    const app = await mountComponent(PublicReadonlySpreadsheet, target, {
        props: session.spreadsheet_public_props,
    });

    odoo.isReady = true;
    return app;
}
