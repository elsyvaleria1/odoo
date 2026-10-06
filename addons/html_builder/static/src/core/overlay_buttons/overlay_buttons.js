/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class OverlayButtons extends Component {
    static template = "html_builder.OverlayButtons";
    static props = { state: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.state = this.props.state;
    }
}
