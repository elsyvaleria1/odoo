// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { RpcEvent } from "@web/core/events";
import { onModelMutation, UPDATE_METHODS } from "@web/core/network/model_mutation";
import { rpcBus } from "@web/core/network/rpc";
import { stableStringify } from "@web/core/network/rpc_dedup";
import { registry } from "@web/core/registry";

/**
 * @typedef {Object} IrFilter
 * @property {[number, string] | false} user_id
 * @property {string} sort
 * @property {string} context
 * @property {string} name
 * @property {string} domain
 * @property {number} id
 * @property {boolean} is_default
 * @property {string} model_id
 * @property {[number, string] | false} action_id
 * @property {number | false} embedded_action_id
 * @property {number | false} embedded_parent_res_id
 */

/**
 * @typedef {Object} ViewDescription
 * @property {string} [arch]
 * @property {import("@web/views/ir/view_ir_schema").ViewIRNode} [ir]
 * @property {number|false} id
 * @property {number|null} [custom_view_id]
 * @property {Object} [actionMenus]
 * @property {IrFilter[]} [irFilters]
 */

/**
 * @typedef {Object} LoadViewsParams
 * @property {string} resModel
 * @property {[number | false, string][]} views
 * @property {Object} [context]
 */

/**
 * @typedef {Object} LoadViewsOptions
 * @property {number|false} actionId
 * @property {boolean} loadActionMenus
 * @property {boolean} loadIrFilters
 */

/**
 * @typedef {Object} ViewDescriptions
 * @property {Record<string, any>} fields
 * @property {Record<string, any>} relatedModels
 * @property {Record<string, ViewDescription>} views
 */

const GET_VIEWS_MODELS = [
    "ir.ui.view",
    "ir.filters",
    "ir.actions.act_window",
    "ir.actions.report",
    "ir.actions.server",
    "ir.model.fields",
];

const log = makeLogger("web.view");

const RUN_VIEWS_KEY = "web.run_views_requests";

class ViewService {
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {{ orm: any }} services
     */
    constructor(env, { orm }) {
        this.env = env;
        this.orm = orm;
        /** @type {Map<string, any>} */
        this.offered = new Map();
        /** @type {Record<number, any> | null} */
        this._runViews = null;
        this.stopWatching = onModelMutation(
            GET_VIEWS_MODELS,
            () => {
                this.offered.clear();
                rpcBus.trigger(RpcEvent.CLEAR_CACHES, "get_views");
            },
            { methods: [...UPDATE_METHODS, "create_filter"] },
        );
    }

    destroy() {
        this.stopWatching();
        this.stopWatching = () => {};
    }

    /** @returns {{ mobile: boolean, debug: boolean }} */
    requestFlags() {
        return { mobile: Boolean(this.env.isSmall), debug: Boolean(this.env.debug) };
    }

    /**
     * @param {{ model: string, views: any[], context: Object, options: Object }} request
     * @param {any} result
     */
    offerViews(request, result) {
        this.offered.set(stableStringify(request), result);
    }

    /**
     * @param {number} actionId
     * @returns {any}
     */
    knownRunViews(actionId) {
        const request = this.runViewsRequests()[actionId];
        const held =
            request &&
            this.orm.isCached(request.model, "get_views", [], {
                context: request.context,
                views: request.views,
                options: request.options,
            });
        return held ? request : undefined;
    }

    /**
     * @param {number} actionId
     * @param {any} request
     */
    rememberRunViews(actionId, request) {
        this._runViews = { ...this.runViewsRequests(), [actionId]: request };
        try {
            browser.localStorage.setItem(RUN_VIEWS_KEY, JSON.stringify(this._runViews));
        } catch {}
    }

    /** @returns {Record<number, any>} */
    runViewsRequests() {
        if (!this._runViews) {
            try {
                this._runViews =
                    JSON.parse(browser.localStorage.getItem(RUN_VIEWS_KEY) || "{}") ||
                    {};
            } catch {
                this._runViews = {};
            }
        }
        return this._runViews;
    }

    /**
     * @param {LoadViewsParams} params
     * @param {LoadViewsOptions} [options={}]
     * @returns {Promise<ViewDescriptions>}
     */
    async loadViews(params, /** @type {any} */ options = {}) {
        const { context, resModel, views } = params;
        const {
            actionId,
            embeddedActionId,
            embeddedParentResId,
            loadIrFilters,
            loadActionMenus,
            ...forwardedOptions
        } = options;
        const loadViewsOptions = {
            action_id: actionId || false,
            embedded_action_id: embeddedActionId || false,
            embedded_parent_res_id: embeddedParentResId || false,
            load_filters: loadIrFilters || false,
            toolbar: (!context?.disable_toolbar && loadActionMenus) || false,
            arch: false,
            ...forwardedOptions,
        };
        const { mobile, debug } = this.requestFlags();
        if (mobile) {
            loadViewsOptions.mobile = true;
        }
        if (debug) {
            loadViewsOptions.debug = true;
        }
        const filteredContext = Object.fromEntries(
            Object.entries(context || {}).filter(
                ([k]) => k === "lang" || k.endsWith("_view_ref"),
            ),
        );

        const requestKey = stableStringify({
            model: resModel,
            views,
            context: filteredContext,
            options: loadViewsOptions,
        });
        const offered = this.offered.get(requestKey);
        this.offered.delete(requestKey);
        log.logic("offered views", () => ({ resModel, taken: offered !== undefined }));

        const endViews = log.perf(`get_views ${resModel}`);
        let result;
        try {
            result = await this.orm
                .cache({
                    type: "disk",
                    ...(offered !== undefined && { fetch: async () => offered }),
                })
                .retry(1)
                .call(resModel, "get_views", [], {
                    context: filteredContext,
                    views,
                    options: loadViewsOptions,
                });
        } catch (error) {
            endViews({ views, options: loadViewsOptions, failed: true });
            throw error;
        }
        endViews({
            views,
            models: Object.keys(result.models).length,
            options: loadViewsOptions,
        });
        /** @type {any} */
        const viewDescriptions = {
            fields: result.models[resModel].fields,
            relatedModels: result.models,
            views: {},
        };
        for (const viewType of Object.keys(result.views)) {
            const { arch, ir, toolbar, id, filters, custom_view_id } =
                result.views[viewType];
            const viewDescription = { arch, ir, id, custom_view_id };
            if (toolbar) {
                viewDescription.actionMenus = toolbar;
            }
            if (filters) {
                viewDescription.irFilters = filters;
            }
            viewDescriptions.views[viewType] = viewDescription;
        }
        return viewDescriptions;
    }
}

export const viewService = {
    dependencies: ["orm"],
    async: ["loadViews"],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {{ orm: any }} services
     * @returns {ViewService}
     */
    start(env, services) {
        return new ViewService(env, services);
    },
};

registry.category("services").add("view", viewService);
