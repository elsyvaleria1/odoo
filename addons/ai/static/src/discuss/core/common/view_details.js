/** @odoo-module native */

/**
 * @param {import("@web/env").OdooEnv} env
 * @returns {Record<string, any> | null}
 */
export function getCurrentViewInfo(env) {
    const view = env.services.active_view?.current;
    if (!view || view.config.viewType === "form") {
        return null;
    }
    const { config, searchModel } = view;
    return {
        action_id: config.actionId,
        view_id: config.viewId,
        model: searchModel.resModel,
        available_view_types: (config.viewSwitcherEntries || []).map((v) => v.type),
        view_type: config.viewType,
        order_by: searchModel.orderBy,
        facets: searchModel.facets,
    };
}
