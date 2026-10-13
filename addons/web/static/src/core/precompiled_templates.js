// @ts-check
/** @odoo-module native */

import { TemplateSet } from "@odoo/owl";
import { assets, loadJS } from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { templates } from "@web/core/templates";
import { makeAssetLog } from "@web/core/utils/asset_log";
import { url } from "@web/core/utils/urls";
import { session } from "@web/session";

const log = makeAssetLog("precompiled_templates");

const LOAD_WAIT_MS = 500;

/** @returns {Promise<unknown>} */
function ensureCompiler() {
    return TemplateSet.compiler
        ? Promise.resolve()
        : assets.loadESMBundle(["@odoo/owl/compiler"]);
}

/**
 * @param {string} bundle
 * @param {string} checksum
 * @param {{ code: string, translationsHash?: string }} localization
 * @param {boolean} [dev]
 * @param {Record<string, any>} [params]
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
        const strict = Boolean(session.await_precompiled_templates);
        if (!localization.translationsHash || (dev && !strict)) {
            await ensureCompiler();
            return;
        }
        if (session.precompiled_templates === false) {
            log("the server has no template precompiler, compiling in the browser");
            await ensureCompiler();
            return;
        }
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
                        url(
                            precompiledTemplatesUrl(
                                bundle,
                                checksum,
                                localization,
                                variant,
                                params,
                            ),
                        ),
                    ).catch((error) => {
                        log("unavailable, compiling in the browser", bundle, error);
                        return ensureCompiler();
                    }),
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
        const arrived = await Promise.race([
            loaded.then(() => true),
            new Promise((resolve) =>
                browser.setTimeout(() => resolve(false), LOAD_WAIT_MS),
            ),
        ]);
        if (!arrived) {
            await ensureCompiler();
        }
    },
};

registry.category("services").add("precompiled_templates", precompiledTemplatesService);
