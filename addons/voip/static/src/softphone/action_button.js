/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class ActionButton extends Component {
    static props = {
        extraClass: t.string().optional(""),
        hideLabel: t.boolean().optional(),
        icon: t.string(),
        name: t.string().optional(),
        onClick: t.function(),
        title: t.string().optional(),
        type: t.string().optional("secondary"),
        inCallPad: t.boolean().optional(),
        disabled: t.boolean().optional(),
        isSmall: t.boolean().optional(),
    };
    static template = "voip.ActionButton";
    props = useProps(this.constructor.props);

    /**
     * Displays the right icon library class depending on the icon defined in
     * the prop.
     *
     * @returns {"fa"|"oi"}
     */
    get iconLib() {
        if (this.props.icon.startsWith("oi-")) {
            return "oi";
        }
        return "fa";
    }
}
