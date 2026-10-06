/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";

export class FieldSelectorDialog extends Component {
    static template = "web_studio.FieldSelectorDialog";
    static components = { Dialog };
    static props = {
        close: t.function(),
        onConfirm: t.function(),
        fields: t.array(),
        showNew: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.debug = useDebugMode();
        this.selectRef = elementRef();
    }
    onConfirm() {
        const field = this.selectRef.el.value;
        this.props.onConfirm(field);
        this.props.close();
    }
    onCancel() {
        this.props.close();
    }
}
