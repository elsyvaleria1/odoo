/** @odoo-module native */
import { Component, proxy, t, useProps, xml } from "@odoo/owl";
import { SidebarPropertiesToolbox } from "@web_studio/client_action/view_editor/interactive_editor/properties/sidebar_properties_toolbox/sidebar_properties_toolbox";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

class DefaultProperties extends Component {
    static props = { node: t.object() };
    static template = xml`
        <SidebarPropertiesToolbox/>
    `;
    static components = { SidebarPropertiesToolbox };
    props = useProps(this.constructor.props);
}

export class Properties extends Component {
    static template = "web_studio.ViewEditor.InteractiveEditorProperties";
    static props = { propertiesComponents: t.object() };
    static components = { DefaultProperties };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
    }

    get iconClass() {
        // first check if the structure has a dedicated icon
        let icon =
            this.viewEditorModel.editorInfo.editor.Sidebar.viewStructures?.[
                this.nodeType
            ]?.class;
        if (!icon && this.nodeType === "field") {
            icon = `o_web_studio_field_${this.node.field.type}`;
        }
        return icon || `o_web_studio_field_${this.nodeType}`;
    }

    get node() {
        return this.viewEditorModel.activeNode;
    }

    get propertiesComponent() {
        return this.props.propertiesComponents[this.nodeType] || {};
    }

    get nodeType() {
        return this.node?.arch.tagName;
    }
}
