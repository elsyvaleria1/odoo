/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { Property } from "@web_studio/client_action/view_editor/property/property";

export class ClassAttribute extends Component {
    static template = "web_studio.ViewEditor.ClassAttribute";
    static components = {
        Property,
    };
    static props = { value: t.string().optional(), onChange: t.function() };
    props = useProps(this.constructor.props);
    get tooltip() {
        return _t(
            "Use Bootstrap or any other custom classes to customize the style and the display of the element.",
        );
    }
}
