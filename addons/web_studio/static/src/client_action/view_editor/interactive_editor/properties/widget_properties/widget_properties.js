/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { ClassAttribute } from "@web_studio/client_action/view_editor/interactive_editor/properties/class_attribute/class_attribute";
import { TypeWidgetProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/type_widget_properties/type_widget_properties";
import { ViewStructureProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/view_structure_properties/view_structure_properties";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useEditNodeAttributes } from "@web_studio/client_action/view_editor/view_editor_model";

export class WidgetProperties extends Component {
    static template = "web_studio.ViewEditor.InteractiveEditorProperties.Widget";
    static components = {
        ClassAttribute,
        Property,
        TypeWidgetProperties,
        ViewStructureProperties,
    };
    static props = { node: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.editNodeAttributes = useEditNodeAttributes();
    }

    onChangeAttribute(value, name) {
        return this.editNodeAttributes({ [name]: value });
    }
}
