/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { SidebarPropertiesToolbox } from "@web_studio/client_action/view_editor/interactive_editor/properties/sidebar_properties_toolbox/sidebar_properties_toolbox";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class MenuProperties extends Component {
    static template = "web_studio.ViewEditor.InteractiveEditorProperties.Menu";
    static components = {
        Property,
        SidebarPropertiesToolbox,
    };
    static props = { node: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        super.setup();
        this.viewEditorModel = useCurrentViewEditorModel();
    }

    // the tree the compiler stamps `studioXpath` on is the parser's copy
    // (archInfo.xmlDoc), not the arch element the editor was mounted from
    get colorPicker() {
        return this.viewEditorModel.controllerProps.archInfo.xmlDoc.querySelector(
            "field[widget=kanban_color_picker]",
        );
    }
    editColorPicker() {
        this.viewEditorModel.activeNodeXpath =
            this.colorPicker.getAttribute("studioXpath");
    }
}
