// @ts-check
/** @odoo-module native */

import { loadCSS } from "@web/core/assets";
import { makeLazyLib } from "@web/core/lib/lazy_lib";

const LEAFLET_CSS = "/web/static/lib/leaflet/leaflet.css";

const leaflet = makeLazyLib(async () => {
    const [module] = await Promise.all([import("leaflet"), loadCSS(LEAFLET_CSS)]);
    return module;
});

/** @type {any} */
export const L = leaflet.facade;

/** @returns {Promise<any>} */
export function loadLeaflet() {
    return leafletLoader.load();
}

export const leafletLoader = {
    /** @returns {Promise<any>} */
    load: () => leaflet.load(),
};
