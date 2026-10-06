/** @odoo-module native */
import { Component, useProps, whenReady } from "@odoo/owl";
import { OdooLogo } from "@point_of_sale/app/components/odoo_logo/odoo_logo";
import { Orders } from "@pos_order_tracking_display/app/components/orders/orders";
import { mountComponent } from "@web/env";

import { useOrderStatusDisplay } from "./services/order_tracking_display_service.js";

export class OrderStatusDisplay extends Component {
    static template = "pos_order_tracking_display.OrderStatusDisplay";
    static components = { Orders, OdooLogo };
    static props = {};
    props = useProps(this.constructor.props);
    setup() {
        this.orders = useOrderStatusDisplay();
    }
}
whenReady(() => mountComponent(OrderStatusDisplay, document.body));
