/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class BackButton extends Component {
    static template = "point_of_sale.BackButton";
    static props = { onClick: t.function(), class: t.object().optional() };
    props = useProps(this.constructor.props);
}
