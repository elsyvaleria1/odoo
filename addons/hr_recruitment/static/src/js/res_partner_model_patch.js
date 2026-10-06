/** @odoo-module native */
import { fields } from "@mail/core/common/record";
import { ResPartner } from "@mail/core/common/res_partner_model";
import { patch } from "@web/core/utils/patch";

patch(ResPartner.prototype, {
    setup() {
        super.setup(...arguments);
        this.applicant_ids = fields.Many("hr.applicant", { inverse: "partner_id" });
    },
});
