/** @odoo-module native */
import "@mail/discuss/call/common/thread_actions";

import { LivechatCommandDialog } from "@im_livechat/core/common/livechat_command_dialog";
import { registerThreadAction } from "@mail/core/common/thread_actions";
import { mailContextOf } from "@mail/utils/common/mail_context";
import { _t } from "@web/core/translation";
import { usePopover } from "@web/ui/popover";

registerThreadAction("create-ticket", {
    actionPanelComponent: LivechatCommandDialog,
    actionPanelComponentProps: ({ action }) => ({
        close: () => action.close(),
        commandName: "ticket",
        placeholderText: _t("e.g. Product arrived damaged"),
        title: _t("Create Ticket"),
        icon: "fa-solid fa-life-ring",
    }),
    close: ({ action }) => action.popover?.close(),
    condition: false,
    panelOuterClass: "bg-100",
    icon: "fa-solid fa-life-ring",
    name: _t("Create Ticket"),
    sequence: 15,
    sequenceGroup: 25,
    setup({ owner }) {
        if (!mailContextOf(owner).inChatWindow) {
            this.popover = usePopover(LivechatCommandDialog, {
                onClose: () => this.close(),
                class: this.panelOuterClass,
            });
        }
    },
    toggle: true,
    open({ owner, thread }) {
        this.popover?.open(owner.root.el.querySelector(`[name="${this.id}"]`), {
            thread,
            ...this.actionPanelComponentProps,
        });
    },
});
