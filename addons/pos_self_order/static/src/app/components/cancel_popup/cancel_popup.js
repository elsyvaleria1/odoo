/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useSelfOrder } from "@pos_self_order/app/services/self_order_service";

export class CancelPopup extends Component {
    static template = "pos_self_order.CancelPopup";
    static props = { title: t.string(), confirm: t.function(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.selfOrder = useSelfOrder();
    }

    confirm() {
        this.props.close();
        this.props.confirm();
    }
}
