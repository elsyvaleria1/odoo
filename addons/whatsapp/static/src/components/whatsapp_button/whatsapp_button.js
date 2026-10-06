/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class SendWhatsAppButton extends Component {
    static template = "whatsapp.SendWhatsAppButton";
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.title = _t("Send WhatsApp Message");
    }

    async onClick() {
        await this.props.record.save();
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                target: "new",
                name: this.title,
                res_model: "wizard.whatsapp.message.send",
                views: [[false, "form"]],
                context: {
                    ...user.context,
                    active_model: this.props.record.resModel,
                    active_id: this.props.record.resId,
                    default_phone: this.props.record.data[this.props.name],
                },
            },
            {
                onClose: () => {
                    this.props.record.load();
                    this.props.record.model.notify();
                },
            },
        );
    }
}
