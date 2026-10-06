/** @odoo-module native */

import { AttachmentList } from "@mail/core/common/attachment_list";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(AttachmentList.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
    },
    async onClickAttachment(attachment) {
        if (attachment.mimetype === "application/o-spreadsheet") {
            await this.openSpreadsheet(attachment);
        } else {
            super.onClickAttachment(attachment);
        }
    },
    async openSpreadsheet(attachment) {
        if (attachment.mimetype === "application/o-spreadsheet") {
            const [spreadsheetId] = await this.orm.search(
                "document.document",
                [["attachment_id", "=", attachment.id]],
                { limit: 1 },
            );
            if (spreadsheetId) {
                this.action.doAction({
                    type: "ir.actions.client",
                    tag: "action_view_spreadsheet",
                    params: {
                        spreadsheet_id: spreadsheetId,
                    },
                });
            }
        }
    },
});
