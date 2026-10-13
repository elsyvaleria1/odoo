/** @odoo-module native */
import { useService, useServices } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { PhoneField } from "@web/fields/basic/phone/phone_field";

patch(PhoneField.prototype, {
    setup() {
        super.setup();
        this.appServices = useServices();
        if ("voip" in this.appServices) {
            this.voip = useService("voip");
            this.callService = useService("voip.call");
            this.userAgent = useService("voip.user_agent");
        }
    },
    /**
     * @private
     * @param {MouseEvent} ev
     */
    onLinkClicked(ev) {
        if (!this.voip?.canCall) {
            return;
        }
        if (ev.target.matches("a")) {
            ev.stopImmediatePropagation();
        }
        ev.preventDefault();
        const fieldName = ev.target.closest(".o_field_phone").getAttribute("name");
        const { record } = this.props;
        this.userAgent.makeCall({
            phone_number: record.data[fieldName],
            res_id: record.resId,
            res_model: record.resModel,
        });
    },
});
