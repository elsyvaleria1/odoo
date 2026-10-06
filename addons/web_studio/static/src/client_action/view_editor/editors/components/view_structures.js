/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { SidebarDraggableItem } from "@web_studio/client_action/components/sidebar_draggable_item/sidebar_draggable_item";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class ViewStructures extends Component {
    static components = { SidebarDraggableItem };
    static template = "web_studio.ViewStructures";
    static props = { structures: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        super.setup();
        this.viewEditorModel = useCurrentViewEditorModel();
    }

    get isVisible() {
        return Object.values(this.props.structures).filter(
            (e) => !e.isVisible || e.isVisible(this.viewEditorModel),
        ).length;
    }
}
