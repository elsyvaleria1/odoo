/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class EmbeddedViewLinkPopover extends Component {
    static template = "knowledge.EmbeddedViewLinkPopover";
    static props = {
        close: t.function(),
        name: t.string(),
        onCopyViewLinkClick: t.function(),
        onEditViewLinkClick: t.function(),
        onRemoveViewLinkClick: t.function(),
        openViewLink: t.function(),
    };
    props = useProps(this.constructor.props);
}
