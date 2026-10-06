/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";
export class OnlinePaymentPopup extends Component {
    static template = "pos_online_payment.OnlinePaymentPopup";
    static components = { Dialog };
    static props = {
        qrCode: t.string(),
        formattedAmount: t.string(),
        orderName: t.string(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);
}
