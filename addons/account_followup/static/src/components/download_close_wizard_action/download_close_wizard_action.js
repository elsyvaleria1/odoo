/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

export async function downloadAndCloseFollowupWizardAction(env, action) {
    browser.open(action.params.url);
    return { type: "ir.actions.act_window_close" };
}

registry
    .category("actions")
    .add("close_followup_wizard", downloadAndCloseFollowupWizardAction);
