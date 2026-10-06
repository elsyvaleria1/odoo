// @ts-check
/** @odoo-module native */

import { loadCSS } from "@web/core/assets";
import { makeLazyLib } from "@web/core/lib/lazy_lib";

const LEAFLET_CSS = "/web/static/lib/leaflet/leaflet.css";

// the stylesheet travels with the module: a map drawn before it lands has no
// pane positioning and its tiles stack in a column
const leaflet = makeLazyLib(async () => {
    const [module] = await Promise.all([import("leaflet"), loadCSS(LEAFLET_CSS)]);
    return module;
});

/**
 * The Leaflet namespace (`L.map`, `L.marker`…), usable once `loadLeaflet()`
 * resolved.
 *
 * @type {any}
 */
export const L = leaflet.facade;

/**
 * Loads Leaflet and its stylesheet once. Rejects when either cannot load: a
 * failed import() rejects with a TypeError, a failed stylesheet with an
 * AssetsLoadingError.
 *
 * @returns {Promise<any>}
 */
export function loadLeaflet() {
    return leafletLoader.load();
}

/** How Leaflet is fetched; patchable in tests. */
export const leafletLoader = {
    /** @returns {Promise<any>} */
    load: () => leaflet.load(),
};
