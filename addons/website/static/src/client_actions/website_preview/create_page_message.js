/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class CreatePageMessage extends Component {
    static template = "website.CreatePageMessage";
    static props = { createPage: t.function() };
    props = useProps(this.constructor.props);
}
