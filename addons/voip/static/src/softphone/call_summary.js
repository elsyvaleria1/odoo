/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Call } from "@voip/core/call_model";
import { ActionButton } from "@voip/softphone/action_button";
import { ContactInfo } from "@voip/softphone/contact_info";
import { TIME_SIMPLE, toLocaleString } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class CallSummary extends Component {
    static components = { ActionButton, ContactInfo };
    static props = { call: t.instanceOf(Call) };
    static template = "voip.CallSummary";
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.voip = useService("voip");
        this.userAgent = useService("voip.user_agent");
        this.ui = useService("ui");
    }

    /** @returns {Call} */
    get call() {
        return this.props.call;
    }

    /** @returns {string} */
    get statusText() {
        const date = this.call.start_date || this.call.create_date;
        const time = toLocaleString(date, TIME_SIMPLE);
        switch (this.call.state) {
            case "aborted":
                return _t("Call cancelled (%(time)s)", { time });
            case "missed":
                return _t("Call Missed (%(time)s)", { time });
            case "rejected":
                return _t("Call declined (%(time)s)", { time });
            case "terminated":
                return _t("Lasted: %(duration)s", {
                    duration: this.call.durationString,
                });
            default:
                return "✌︎☹︎☹︎☜︎💧︎ ✋︎💧︎ 😐︎✌︎🏱︎⚐︎❄︎";
        }
    }

    /** @param {MouseEvent} ev */
    onClickActivity(ev) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_id: false,
            res_model: "mail.activity",
            views: [[false, "form"]],
            view_mode: "form",
            target: "new",
            context: {
                default_activity_type_id: this.voip.callActivityTypeId,
                default_res_id: this.call.partner_id.id,
                default_res_model: "res.partner",
            },
        });
    }

    /** @param {MouseEvent} ev */
    onClickCall(ev) {
        this.userAgent.makeCall({
            partner: this.call.partner_id,
            phone_number: this.call.phone_number,
        });
    }

    /** @param {MouseEvent} ev */
    onClickContact(ev) {
        const action = {
            type: "ir.actions.act_window",
            res_model: "res.partner",
            views: [[false, "form"]],
            target: this.ui.isSmall ? "new" : "current",
        };
        if (this.call.partner_id) {
            action.res_id = this.call.partner_id.id;
        } else {
            action.context = { default_phone: this.call.phone_number };
        }
        this.action.doAction(action);
    }
}
