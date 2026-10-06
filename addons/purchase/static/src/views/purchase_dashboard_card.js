/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class PurchaseDashboardCard extends Component {
    static template = "purchase.PurchaseDashboardCard";
    static props = {
        label: t.string().optional(),
        title: t.string(),
        emphasis: t.string(),
        values: t.object(),
        position: t.string(),
        onSelected: t.function(),
    };
    props = useProps(this.constructor.props);

    get colorClass() {
        const emphasis = this.props.values.all ? this.props.emphasis : "secondary";
        return `bg-${emphasis}-subtle text-${emphasis}-emphasis`;
    }
}
