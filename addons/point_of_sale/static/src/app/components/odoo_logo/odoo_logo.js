/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class OdooLogo extends Component {
    static template = "point_of_sale.OdooLogo";
    static props = {
        class: t.string().optional(""),
        style: t.string().optional(""),
        monochrome: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);
}
