/** @odoo-module native */

import { helperValue } from "@test_assetsbundle/../tests/esm_inlined/unlisted/helper";

export const value = helperValue;

export function loadLazy() {
    return import("@test_assetsbundle/../tests/esm_inlined/unlisted/lazy");
}
