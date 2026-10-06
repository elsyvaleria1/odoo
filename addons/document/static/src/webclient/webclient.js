/** @odoo-module native */
import { getDocumentActionRequest } from "@document/utils";
import { router } from "@web/core/browser/router";
import { reportUncaught } from "@web/core/errors/error_utils";
import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

patch(WebClient.prototype, {
    /**
     * @override a document's own URL opens the Documents app on it, not its
     * form. Restored here, not in loadRouterState: the app is made the current
     * menu as for any route, and a failure falls back to the default app.
     */
    async _restoreRoute(menuId, storedMenuId) {
        const { resId, model } = router.current.actionStack?.at(-1) || {};
        if (!resId || model !== "document.document") {
            return super._restoreRoute(...arguments);
        }
        try {
            await this.actionService.doAction(getDocumentActionRequest(resId), {
                clearBreadcrumbs: true,
            });
        } catch (error) {
            reportUncaught(error);
            if (!this.actionService.currentController) {
                await this._loadDefaultApp();
            }
            return false;
        }
        const actionId = this.actionService.currentController?.action.id;
        const appId = Number(this.menuService.getAppIdByAction(actionId)) || menuId;
        if (appId) {
            this.menuService.setCurrentMenu(appId);
        }
        return true;
    },
});
