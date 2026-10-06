/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { LimitGroupVisibility } from "@web_studio/client_action/view_editor/interactive_editor/properties/limit_group_visibility/limit_group_visibility";
import { SidebarPropertiesToolbox } from "@web_studio/client_action/view_editor/interactive_editor/properties/sidebar_properties_toolbox/sidebar_properties_toolbox";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class ViewStructureProperties extends Component {
    static components = { LimitGroupVisibility, SidebarPropertiesToolbox };
    static template = "web_studio.ViewStructureProperties";
    static props = { slots: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
    }
}
