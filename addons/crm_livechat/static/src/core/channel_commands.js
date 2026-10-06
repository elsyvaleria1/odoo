/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

registry.category("discuss.channel_commands").add("lead", {
    condition: ({ store }) => store.has_access_livechat,
    help: _t("Create a new lead (/lead lead title)"),
    methodName: "execute_command_lead",
});
