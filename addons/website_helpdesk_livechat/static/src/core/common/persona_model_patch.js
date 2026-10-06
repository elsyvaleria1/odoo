/** @odoo-module native */
import { fields } from "@mail/core/common/record";
import { ResPartner } from "@mail/core/common/res_partner_model";
import { patch } from "@web/core/utils/patch";

patch(ResPartner.prototype, {
    setup() {
        super.setup();
        this.helpdesk_tickets = fields.Many("helpdesk.ticket");
    },
});
