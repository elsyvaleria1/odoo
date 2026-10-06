/** @odoo-module native */
import { ResPartner } from "@mail/core/common/res_partner_model";
import { DATE_MED, deserializeDate, today, toLocaleString } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

/** @param {Temporal.PlainDate | string} leaveDateTo */
export function getOutOfOfficeDateEndText(leaveDateTo) {
    const foptions = { ...DATE_MED };
    const date =
        typeof leaveDateTo === "string" ? deserializeDate(leaveDateTo) : leaveDateTo;
    if (date.year === today().year) {
        foptions.year = undefined;
    }
    const fdate = toLocaleString(date, foptions);
    return _t("Back on %(date)s", { date: fdate });
}

patch(ResPartner.prototype, {
    get outOfOfficeDateEndText() {
        const employee_id = this.employee_id || this.main_user_id?.employee_id;
        if (!employee_id?.leave_date_to) {
            return "";
        }
        return getOutOfOfficeDateEndText(employee_id.leave_date_to);
    },
});
