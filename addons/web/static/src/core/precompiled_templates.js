// @ts-check
/** @odoo-module native */

import { loadJS } from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { templates } from "@web/core/templates";
import { makeAssetLog } from "@web/core/utils/asset_log";
import { session } from "@web/session";

const log = makeAssetLog("precompiled_templates");

const LOAD_WAIT_MS = 500;

/**
 * The translations are compiled into the code, so the artifact is per
 * language and per payload of translations the page runs with; OWL's dev
 * mode generates other code, so it has an artifact of its own.
 *
 * @param {string} bundle
 * @param {string} checksum
 * @param {{ code: string, translationsHash?: string }} localization
 * @param {boolean} [dev]
 * @param {Record<string, any>} [params] the assets params the bundle was built
 *  with (a website's), which the server needs to rebuild it
 */
export function precompiledTemplatesUrl(
    bundle,
    checksum,
    localization,
    dev = false,
    params = {},
) {
    const variant = dev ? ".dev" : "";
    const query = Object.keys(params).length
        ? `?assets_params=${encodeURIComponent(JSON.stringify(params))}`
        : "";
    return `/web/assets/owl/${checksum}/${localization.code}/${localization.translationsHash}/${bundle}${variant}.js${query}`;
}

export const precompiledTemplatesService = {
    dependencies: ["localization"],
    /**
     * @param {any} env
     * @param {{ localization: any }} services
     */
    async start(env, { localization }) {
        const dev = Boolean(env.debug || session.test_mode);
        // a public page may run without 'unsafe-eval': a template it compiles
        // in the browser throws, so it waits for every artifact, in dev mode too
        const strict = Boolean(session.await_precompiled_templates);
        if (!localization.translationsHash || (dev && !strict)) {
            return;
        }
        if (session.precompiled_templates === false) {
            // the server cannot build the artifact: asking would cost it a
            // request and this page the wait for a 404
            log("the server has no template precompiler, compiling in the browser");
            return;
        }
        // renderToString compiles outside dev mode on every page
        const variants = dev ? [false, true] : [false];
        /**
         * @param {string} bundle
         * @param {string} checksum
         * @param {Record<string, any>} params
         */
        const load = (bundle, checksum, params) =>
            Promise.all(
                variants.map((variant) =>
                    loadJS(
                        precompiledTemplatesUrl(
                            bundle,
                            checksum,
                            localization,
                            variant,
                            params,
                        ),
                    ).catch((error) =>
                        log("unavailable, compiling in the browser", bundle, error),
                    ),
                ),
            ).then(() => {});
        templates.bundleListeners.add(
            strict
                ? load
                : (bundle, checksum, params) => {
                      load(bundle, checksum, params);
                  },
        );
        const loaded = Promise.all(
            [...templates.bundles].map(([bundle, { checksum, params }]) =>
                load(bundle, checksum, params),
            ),
        );
        if (strict) {
            await loaded;
            return;
        }
        // a cached artifact arrives within the bound; one the server is still
        // compiling (the first page of a language after a deploy) does not
        // hold the boot: what renders before it compiles in the browser
        await Promise.race([
            loaded,
            new Promise((resolve) => browser.setTimeout(resolve, LOAD_WAIT_MS)),
        ]);
    },
};

registry.category("services").add("precompiled_templates", precompiledTemplatesService);
