// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { onModelMutation } from "@web/core/network";
import { registry } from "@web/core/registry";

export const reloadAnalyticPlanService = {
    dependencies: ["action"],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {{ action: ReturnType<typeof import("@web/webclient/actions/action_service").actionService.start> }} services
     */
    start(env, { action }) {
        const dispose = onModelMutation(
            ["account.analytic.plan"],
            () => {
                if (!browser.localStorage.getItem("running_tour")) {
                    action.doAction("reload_context");
                }
            },
            { successOnly: true },
        );
        return { destroy: dispose };
    },
};

registry.category("services").add("reloadAnalyticPlan", reloadAnalyticPlanService);
