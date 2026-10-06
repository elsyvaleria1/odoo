/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { ActionButton } from "@voip/softphone/action_button";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class SmsButton extends Component {
    static components = { ActionButton };
    static props = { phoneNumber: t.string(), resId: t.number(), resModel: t.string() };
    static template = "voip_sms.SmsButton";
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    onClick() {
        const action = {
            type: "ir.actions.act_window",
            name: _t("Send text message"),
            res_model: "wizard.sms.sms.send",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_number: this.props.phone_number,
            },
        };
        if (this.props.resModel && this.props.resId) {
            Object.assign(action.context, {
                default_res_id: this.props.resId,
                default_res_model: this.props.resModel,
            });
        }
        this.action.doAction(action);
    }
}
