/** @odoo-module native */
import { Component, onWillUpdateProps, t, useProps } from "@odoo/owl";

export class CommentAnchorText extends Component {
    static template = "knowledge.CommentAnchorText";
    static props = { anchorText: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.anchorTextArray = this.props.anchorText.split("<br>");
        onWillUpdateProps((newProps) => {
            this.anchorTextArray = newProps.anchorText.split("<br>");
        });
    }
}
