/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class WarningNotification extends Component {
    static template = "website_sale.warningNotification";
    static props = { warning: t.or([t.string(), t.any()]) };
    props = useProps(this.constructor.props);
}
