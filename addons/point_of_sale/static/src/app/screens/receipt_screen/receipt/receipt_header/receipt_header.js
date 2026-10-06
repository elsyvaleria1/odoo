/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class ReceiptHeader extends Component {
    static template = "point_of_sale.ReceiptHeader";
    static props = { order: t.object() };
    props = useProps(this.constructor.props);

    get order() {
        return this.props.order;
    }

    get logoUrl() {
        return this.order.config.receiptLogoUrl;
    }

    get partnerAddress() {
        return this.order.partner_id.pos_contact_address
            .split("\n")
            .filter((line) => line.trim() !== "")
            .join(", ");
    }
}
