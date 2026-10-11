/** @odoo-module native */
import { router } from "@web/core/browser/router";
import { patch } from "@web/core/utils/patch";

const DOCUMENTS_PATH = /^\/odoo\/documents(?=[/?]|$)/;

patch(router, {
    isServerRoute(url) {
        return url.pathname.startsWith("/odoo/documents/") || super.isServerRoute(url);
    },

    stateToUrl(state) {
        const url = super.stateToUrl(state);
        if (DOCUMENTS_PATH.test(url) && state.access_token) {
            return (
                `/odoo/documents/${encodeURIComponent(state.access_token)}` +
                (Object.hasOwn(state, "debug") ? `?debug=${state.debug}` : "")
            );
        }
        return url;
    },
});
