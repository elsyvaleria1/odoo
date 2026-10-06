/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";

export class SidebarDraggableItem extends Component {
    static template = "web_studio.SidebarDraggableItem";
    static props = {
        className: t.string().optional(),
        description: t.string().optional(),
        dropData: t.any().optional(),
        string: t.string(),
        structure: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.debug = useDebugMode();
    }
}
