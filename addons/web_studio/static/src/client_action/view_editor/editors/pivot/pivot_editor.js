/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { MultiRecordSelector } from "@web/components/record_selectors";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Many2ManyTagsField } from "@web/fields/relational/many2many_tags";
import { pivotView } from "@web/views/pivot";
import { computeReportMeasures } from "@web/views/view_measurements";
import { fieldsToChoices } from "@web_studio/client_action/view_editor/editors/utils";
import { InteractiveEditorSidebar } from "@web_studio/client_action/view_editor/interactive_editor/interactive_editor_sidebar";
import { SidebarViewToolbox } from "@web_studio/client_action/view_editor/interactive_editor/sidebar_view_toolbox/sidebar_view_toolbox";
import * as operationUtils from "@web_studio/client_action/view_editor/operations_utils";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useEditNodeAttributes } from "@web_studio/client_action/view_editor/view_editor_model";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

function getFieldNameFromGroupby(str) {
    return str.split(":")[0];
}

export class PivotEditorSidebar extends Component {
    static template = "web_studio.ViewEditor.PivotEditorSidebar";
    static props = {
        openViewInForm: t.function().optional(),
        openDefaultValues: t.function().optional(),
    };
    static components = {
        InteractiveEditorSidebar,
        Property,
        SidebarViewToolbox,
        Many2ManyTagsField,
        MultiRecordSelector,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.editArchAttributes = useEditNodeAttributes({ isRoot: true });
    }

    get possibleMeasures() {
        const { fieldAttrs, activeMeasures } = this.archInfo;
        return computeReportMeasures(
            this.viewEditorModel.fields,
            fieldAttrs,
            activeMeasures,
        );
    }

    get multiRecordSelectorProps() {
        return {
            resModel: "ir.model.fields",
            update: this.changeMeasureFields.bind(this),
            resIds: this.currentMeasureFields,
            domain: [
                ["model", "=", this.viewEditorModel.resModel],
                ["name", "in", Object.keys(this.possibleMeasures)],
            ],
        };
    }

    get currentMeasureFields() {
        return (
            JSON.parse(
                this.viewEditorModel.xmlDoc.firstElementChild.getAttribute(
                    "studio_pivot_measure_field_ids",
                ),
            ) || []
        );
    }

    get archInfo() {
        return this.viewEditorModel.controllerProps.modelParams.metaData;
    }

    get rowGroupBys() {
        return this.archInfo.rowGroupBys.map((fName) => getFieldNameFromGroupby(fName));
    }

    get colGroupBys() {
        return this.archInfo.colGroupBys.map((fName) => getFieldNameFromGroupby(fName));
    }

    /**
     * @param {Array<Number>} resIds
     */
    changeMeasureFields(resIds) {
        const currentFullIds = this.currentMeasureFields;
        const newIds = resIds.filter((id) => !currentFullIds.includes(id));
        let toRemoveIds;

        const operationType = newIds.length ? "add" : "remove";

        if (operationType === "remove") {
            toRemoveIds = currentFullIds.filter((id) => !resIds.includes(id));
        }

        this.viewEditorModel.doOperation({
            type: "pivot_measures_fields",
            target: {
                operation_type: operationType,
                field_ids: operationType === "add" ? newIds : toRemoveIds,
            },
        });
    }

    onGroupByChanged(type, newValue, oldValue) {
        const operation = operationUtils.viewGroupByOperation(
            "pivot",
            type,
            newValue,
            oldValue,
        );
        this.viewEditorModel.doOperation(operation);
    }

    onViewAttributeChanged(value, name) {
        value = value ? value : "";
        return this.editArchAttributes({ [name]: value });
    }

    get columnGroupbyChoices() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            this.viewEditorModel.GROUPABLE_TYPES,
            (field) =>
                field.groupable &&
                ![this.archInfo.rowGroupBys[0], this.archInfo.rowGroupBys[1]].includes(
                    field.name,
                ),
        );
    }

    get rowGroupbyChoices_first() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            this.viewEditorModel.GROUPABLE_TYPES,
            (field) =>
                field.groupable &&
                ![this.archInfo.colGroupBys[0], this.archInfo.rowGroupBys[1]].includes(
                    field.name,
                ),
        );
    }

    get rowGroupbyChoices_second() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            this.viewEditorModel.GROUPABLE_TYPES,
            (field) =>
                field.groupable &&
                ![this.archInfo.colGroupBys[0], this.archInfo.rowGroupBys[0]].includes(
                    field.name,
                ),
        );
    }
}

registry.category("studio_editors").add("pivot", {
    label: _t("Pivot"),
    icon: "oi oi-view-pivot",
    group: "reporting",
    ...pivotView,
    Sidebar: PivotEditorSidebar,
});
