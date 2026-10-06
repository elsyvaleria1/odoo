/** @odoo-module native */
import { EMBEDDED_VIEW_LINK_STYLES } from "@knowledge/editor/embedded_components/core/embedded_view_link/embedded_view_link_style";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";

export class EmbeddedViewLinkEditDialog extends Component {
    static template = "knowledge.EmbeddedViewLinkEditDialog";
    static components = { Dialog };
    static props = {
        style: t.string(),
        close: t.function(),
        name: t.string(),
        onSave: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            name: this.props.name,
            style: this.props.style,
        });
        this.input = elementRef();
    }

    //--------------------------------------------------------------------------
    // GETTERS/SETTERS
    //--------------------------------------------------------------------------

    get name() {
        return this.state.name.trim();
    }

    get styles() {
        return EMBEDDED_VIEW_LINK_STYLES;
    }

    //--------------------------------------------------------------------------
    // HANDLERS
    //--------------------------------------------------------------------------

    onConfirm() {
        if (!this.name) {
            return this.input.el.focus();
        }
        this.props.onSave(this.name, this.state.style);
        this.props.close();
    }

    updateStyle(style) {
        this.state.style = style;
    }
}
