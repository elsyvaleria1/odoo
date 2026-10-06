/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useForwardRefToParent } from "@web/core/utils/hooks";

export class EmbeddedComponentToolbar extends Component {
    static props = { buttonsGroupClass: t.string().optional(), slots: t.object() };
    static template = "html_editor.EmbeddedComponentToolbar";
    props = useProps(this.constructor.props);
}

export class EmbeddedComponentToolbarButton extends Component {
    static props = {
        buttonRef: t.function().optional(),
        hidden: t.boolean().optional(),
        icon: t.string().optional(),
        label: t.string(),
        name: t.string().optional(),
        onClick: t.function(),
        title: t.string().optional(),
    };
    static template = "html_editor.EmbeddedComponentToolbarButton";
    props = useProps(this.constructor.props);

    setup() {
        this.buttonRefRef = elementRef();
        useForwardRefToParent("buttonRef", this.buttonRefRef);
    }
}
