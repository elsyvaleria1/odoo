/** @odoo-module native */
import { getDocumentActionRequest } from "@document/utils";
import { router } from "@web/core/browser/router";
import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

patch(WebClient.prototype, {
    /**
     * @override to
     */
    loadRouterState() {
        const { resId, model } = router.current.actionStack?.at(-1) || {};
        if (resId && model === "document.document") {
            return this.actionService.doAction(getDocumentActionRequest(resId));
        }
        return super.loadRouterState(...arguments);
    },
});
