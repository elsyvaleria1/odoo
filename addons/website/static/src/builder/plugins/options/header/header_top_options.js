/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class HeaderTopOptions extends Component {
    static template = "website.HeaderTopOptions";
    static props = { openEditMenu: t.function() };
    props = useProps(this.constructor.props);
}
