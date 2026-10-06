/** @odoo-module native */
import { Activity } from "@mail/core/web/activity";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(Activity.prototype, {
    setup() {
        super.setup(...arguments);
        this.userAgent = useService("voip.user_agent");
        this.store = useService("mail.store");
    },

    /**
     * @param {MouseEvent} ev
     * @param {string} phoneNumber
     */
    onClickPhoneNumber(ev, phoneNumber) {
        ev.preventDefault();
        this.userAgent.makeCall({
            activity: this.store["mail.activity"].get(this.props.activity.id),
            phone_number: phoneNumber,
            res_id: this.props.activity.res_id,
            res_model: this.props.activity.res_model,
        });
    },
});
