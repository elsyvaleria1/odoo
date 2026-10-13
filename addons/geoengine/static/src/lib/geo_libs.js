/** @odoo-module native */

/** @type {{ol: Object | null, chroma: Function | null, geostats: Function | null}} */
const loaded = { ol: null, chroma: null, geostats: null };

/**
 * @param {"ol" | "chroma" | "geostats"} name
 * @returns {any}
 */
function forwardTo(name) {
    const current = () => {
        const lib = loaded[name];
        if (lib === null) {
            throw new Error(
                `${name} used before loadGeoLibs() resolved -- await it first.`,
            );
        }
        return lib;
    };
    return new Proxy(function () {}, {
        get: (_target, key) => Reflect.get(current(), key),
        has: (_target, key) => Reflect.has(current(), key),
        apply: (_target, thisArg, args) => Reflect.apply(current(), thisArg, args),
        construct: (_target, args) => Reflect.construct(current(), args),
    });
}

/** @type {typeof import("ol")} */
export const ol = forwardTo("ol");

/** @type {Function} */
export const chroma = forwardTo("chroma");

/** @type {Function} */
export const geostats = forwardTo("geostats");

/** @type {Promise<void> | null} */
let loadPromise = null;

/**
 * @returns {Promise<void>}
 */
export function loadGeoLibs() {
    loadPromise ??= Promise.all([import("ol"), import("chroma-js"), import("geostats")])
        .then(([olModule, chromaModule, geostatsModule]) => {
            loaded.ol = olModule;
            loaded.chroma = chromaModule.default;
            loaded.geostats = geostatsModule.default;
        })
        .catch((error) => {
            loadPromise = null;
            throw error;
        });
    return loadPromise;
}

/**
 * @returns {{ol: Object, chroma: Function, geostats: Function}}
 * @throws {Error}
 */
export function geoLibs() {
    if (!areGeoLibsLoaded()) {
        throw new Error(
            "geoLibs() called before loadGeoLibs() resolved -- await it first.",
        );
    }
    return { ...loaded };
}

/**
 * @returns {boolean}
 */
export function areGeoLibsLoaded() {
    return loaded.ol !== null && loaded.chroma !== null && loaded.geostats !== null;
}

/**
 * @param {{code: string, proj4: string, extent: number[]|null}[]} definitions
 * @returns {Promise<void>}
 */
export async function registerProjections(definitions) {
    const missing = (definitions || []).filter(({ code }) => !ol.proj.get(code));
    if (!missing.length) {
        return;
    }
    const { default: proj4 } = await import("proj4");
    for (const { code, proj4: definition } of missing) {
        proj4.defs(code, definition);
    }
    ol.proj.register(proj4);
    for (const { code, extent } of missing) {
        if (extent) {
            ol.proj.get(code).setExtent(extent);
        }
    }
}
