/** @odoo-module native */
import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/translation";

registerThreadAction("telegram-connect-group", {
    condition: ({ thread }) =>
        thread?.channel?.channel_type === "telegram" &&
        !thread.channel.parent_channel_id &&
        Boolean(thread.channel.self_member_id),
    icon: "fa-brands fa-telegram",
    name: _t("Connect a Telegram Group"),
    open: ({ owner, thread }) =>
        owner.env.services.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Connect a Telegram Group"),
            res_model: "wizard.telegram.group.link",
            views: [[false, "form"]],
            target: "new",
            context: { default_channel_id: thread.channel.id },
        }),
    sequence: 40,
    sequenceGroup: 30,
});
