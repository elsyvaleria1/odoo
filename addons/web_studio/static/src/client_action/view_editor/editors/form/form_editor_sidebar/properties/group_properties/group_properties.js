/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { ModifiersProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/modifiers/modifiers_properties";
import { ViewStructureProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/view_structure_properties/view_structure_properties";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useEditNodeAttributes } from "@web_studio/client_action/view_editor/view_editor_model";

export class GroupProperties extends Component {
    static template = "web_studio.ViewEditor.InteractiveEditorProperties.Group";
    static components = {
        ModifiersProperties,
        Property,
        ViewStructureProperties,
    };
    static props = { node: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.editNodeAttributes = useEditNodeAttributes();
    }

    onChangeAttribute(value, name) {
        return this.editNodeAttributes({ [name]: value });
    }
}
