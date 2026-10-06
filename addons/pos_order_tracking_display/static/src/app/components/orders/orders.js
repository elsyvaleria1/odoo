/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class Orders extends Component {
    static template = "pos_order_tracking_display.Orders";
    static props = {
        class: t.string().optional(""),
        categoryName: t.string(),
        orders: t.array(),
        ready: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);
}
