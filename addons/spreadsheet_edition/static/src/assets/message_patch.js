/** @odoo-module native */
import "@mail/core/web/message_patch"; // dependency ordering

import { Message } from "@mail/core/common/message";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(Message.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
    },

    /**
     * This function overrides the original method so that when the user tries to open a the record
     * from a starred discussion linked to a spreadsheet cell thread, it can be redirected to the corresponding
     * spreadsheet record.
     * @override
     */
    async openRecord() {
        if (this.message.model === "spreadsheet.cell.thread") {
            const action = await this.orm.call(
                "spreadsheet.cell.thread",
                "get_spreadsheet_access_action",
                [this.message.thread.id],
            );
            this.action.doAction(action);
            return;
        } else {
            super.openRecord();
        }
    },
});
