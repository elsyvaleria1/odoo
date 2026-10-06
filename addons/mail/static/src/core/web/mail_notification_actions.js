// @ts-check
/** @odoo-module native */
import { registry } from "@web/core/registry";

registry.category("actions").add(
    "action_send_mail_callback",
    /** @param {import("@web/env").OdooEnv} env */
    async (env) => {
        await env.services.action.doAction({ type: "ir.actions.act_window_close" });
    },
);
