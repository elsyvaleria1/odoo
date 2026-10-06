/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { formatCurrency } from "@web/core/currency";

export class BadgeExtraPrice extends Component {
    static template = "sale.BadgeExtraPrice";
    static props = { price: t.number(), currencyId: t.number() };
    props = useProps(this.constructor.props);

    /** @return {String} */
    getFormattedPrice() {
        return formatCurrency(Math.abs(this.props.price), this.props.currencyId);
    }
}
