/** @odoo-module native */
import LineComponent from "@stock_barcode/components/line";
import { deserializeDateTime, formatDate } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(LineComponent.prototype, {
    get isUseExpirationDate() {
        return this.line.product_id.use_expiration_date;
    },

    get expirationDate() {
        const dateTimeStrUTC =
            (this.line.trace_id && this.line.trace_id.expiration_date) ||
            this.line.expiration_date;
        if (!dateTimeStrUTC) {
            return "";
        }
        return formatDate(deserializeDateTime(dateTimeStrUTC));
    },
});
