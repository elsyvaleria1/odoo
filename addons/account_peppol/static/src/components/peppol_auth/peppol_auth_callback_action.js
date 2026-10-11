/** @odoo-module native */
import { registry } from "@web/core/registry";

export async function PeppolAuthCallbackAction(env, action) {
    const params = action.params || {};
    if (window.opener && window.opener.odoo) {
        window.close();
    }
    return params.next;
}

registry
    .category("actions")
    .add("action_peppol_auth_callback", PeppolAuthCallbackAction);
