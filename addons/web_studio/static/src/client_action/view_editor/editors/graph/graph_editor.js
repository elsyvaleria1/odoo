/** @odoo-module native */
import { Component, onWillPatch, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { graphView } from "@web/views/graph";
import { fieldsToChoices } from "@web_studio/client_action/view_editor/editors/utils";
import { InteractiveEditorSidebar } from "@web_studio/client_action/view_editor/interactive_editor/interactive_editor_sidebar";
import { SidebarViewToolbox } from "@web_studio/client_action/view_editor/interactive_editor/sidebar_view_toolbox/sidebar_view_toolbox";
import * as operationUtils from "@web_studio/client_action/view_editor/operations_utils";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useEditNodeAttributes } from "@web_studio/client_action/view_editor/view_editor_model";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class GraphEditorSidebar extends Component {
    static template = "web_studio.ViewEditor.GraphEditorSidebar";
    static props = {
        openViewInForm: t.function().optional(),
        openDefaultValues: t.function().optional(),
    };
    static components = {
        InteractiveEditorSidebar,
        Property,
        SidebarViewToolbox,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.editArchAttributes = useEditNodeAttributes({ isRoot: true });

        onWillPatch(() => {
            this.oldFieldValues = {
                firstDimension: this.modelParams.groupBy[0],
                secondDimension: this.modelParams.groupBy[1],
                measure:
                    this.modelParams.measure === "__count"
                        ? undefined
                        : this.modelParams.measure,
            };
        });
    }

    onViewAttributeChanged(value, name) {
        value = value ? value : "";
        return this.editArchAttributes({ [name]: value });
    }

    onGroupByChanged(type, newField, oldField) {
        const operation = operationUtils.viewGroupByOperation(
            "graph",
            type,
            newField,
            oldField,
        );
        this.viewEditorModel.doOperation(operation);
    }

    get modelParams() {
        return this.viewEditorModel.controllerProps.modelParams;
    }

    get typeChoices() {
        return [
            { label: _t("Bar"), value: "bar" },
            { label: _t("Line"), value: "line" },
            { label: _t("Pie"), value: "pie" },
        ];
    }

    get orderChoices() {
        return [
            { label: _t("Ascending"), value: "asc" },
            { label: _t("Descending"), value: "desc" },
        ];
    }

    get firstGroupbyChoices() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            this.viewEditorModel.GROUPABLE_TYPES,
            (field) => field.groupable && field.name !== this.modelParams.groupBy[1],
        );
    }

    get secondGroupbyChoices() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            this.viewEditorModel.GROUPABLE_TYPES,
            (field) => field.groupable && field.name !== this.modelParams.groupBy[0],
        );
    }

    get mesureChoices() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            ["integer", "float", "monetary"],
            (field) => field.aggregator && field.name !== "id",
        );
    }
}

registry.category("studio_editors").add("graph", {
    label: _t("Graph"),
    icon: "fa-solid fa-chart-area",
    group: "reporting",
    ...graphView,
    Sidebar: GraphEditorSidebar,
});
