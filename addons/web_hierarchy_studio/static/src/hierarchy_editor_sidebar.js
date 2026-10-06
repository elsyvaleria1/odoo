/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { hierarchyView } from "@web_hierarchy/hierarchy_view";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";
import {
    InteractiveEditorSidebar,
    Property,
    SidebarViewToolbox,
    useEditNodeAttributes,
} from "@web_studio/editor";

export class HierarchyEditorSidebar extends Component {
    static template = "web_hierarchy_studio.HierarchyEditorSidebar";
    static props = {
        openViewInForm: t.function().optional(),
        openDefaultValues: t.function().optional(),
    };
    static components = { InteractiveEditorSidebar, Property, SidebarViewToolbox };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.editArchAttributes = useEditNodeAttributes({ isRoot: true });
    }

    get archInfo() {
        return this.viewEditorModel.controllerProps.archInfo;
    }

    // The root attributes HIERARCHY_VALID_ATTRIBUTES admits and the parser
    // reads. The card is a `hierarchy-box` template, edited as XML.
    get parentFieldChoices() {
        const resModel = this.viewEditorModel.resModel;
        return Object.values(this.viewEditorModel.fields)
            .filter((field) => field.type === "many2one" && field.relation === resModel)
            .map((field) => ({
                label: `${field.string} (${field.name})`,
                value: field.name,
            }));
    }

    get childFieldChoices() {
        const resModel = this.viewEditorModel.resModel;
        return Object.values(this.viewEditorModel.fields)
            .filter((field) => field.type === "one2many" && field.relation === resModel)
            .map((field) => ({
                label: `${field.string} (${field.name})`,
                value: field.name,
            }));
    }

    get defaultOrderChoices() {
        return Object.values(this.viewEditorModel.fields)
            .filter((field) => field.store && field.sortable !== false)
            .map((field) => ({
                label: `${field.string} (${field.name})`,
                value: field.name,
            }));
    }

    onViewAttributeChanged(value, name) {
        return this.editArchAttributes({ [name]: value ?? "" });
    }

    onDraggableChanged(value) {
        return this.editArchAttributes({ draggable: value ? "1" : "0" });
    }
}

registry.category("studio_editors").add("hierarchy", {
    ...hierarchyView,
    label: _t("Hierarchy"),
    icon: "fa-solid fa-share-alt fa-rotate-90",
    group: "multiple",
    Sidebar: HierarchyEditorSidebar,
});
