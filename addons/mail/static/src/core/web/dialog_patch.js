// @ts-check
/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/ui/dialog";
patch(Dialog.prototype, {
    onEscape() {
        const messageModels = ["wizard.mail.message.send", "mail.scheduled.message"];
        if (messageModels.includes(this.data.model)) {
            return;
        }
        super.onEscape();
    },
});
