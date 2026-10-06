/** @odoo-module native */
import { Message } from "@mail/core/common/message";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(Message.prototype, {
    formatAccountReportsAnnotationDate(date) {
        return formatDate(deserializeDate(date));
    },
});
