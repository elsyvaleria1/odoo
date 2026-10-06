/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { MultiRecordSelector } from "@web/components/record_selectors";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Many2ManyTagsField } from "@web/fields/relational/many2many_tags";
import { mapView } from "@web_map/map_view/map_view";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";
import {
    fieldsToChoices,
    InteractiveEditorSidebar,
    Property,
    SidebarViewToolbox,
    useEditNodeAttributes,
} from "@web_studio/editor";

import { MapNewViewDialog } from "./map_new_view_dialog.js";

export class MapEditorSidebar extends Component {
    static template = "web_map_studio.MapEditorSidebar";
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

    get modelParams() {
        return this.viewEditorModel.controllerProps.modelParams;
    }

    get multiRecordSelectorProps() {
        return {
            resModel: "ir.model.fields",
            update: this.changeAdditionalFields.bind(this),
            resIds: this.currentAdditionalFieldsIds,
            domain: [
                ["model", "=", this.viewEditorModel.resModel],
                ["ttype", "not in", ["many2many", "one2many", "binary"]],
            ],
        };
    }

    get currentAdditionalFieldsIds() {
        return (
            JSON.parse(
                this.viewEditorModel.xmlDoc.firstElementChild.getAttribute(
                    "studio_map_field_ids",
                ),
            ) || []
        );
    }

    onViewAttributeChanged(value, name) {
        value = value ? value : "";
        return this.editArchAttributes({ [name]: value });
    }

    get contactFieldChoices() {
        return Object.values(this.viewEditorModel.fields)
            .filter(
                (field) =>
                    field.type === "many2one" && field.relation === "res.partner",
            )
            .map((field) => ({
                label: `${field.string} (${field.name})`,
                value: field.name,
            }));
    }

    get defaultOrderChoices() {
        return Object.values(this.viewEditorModel.fields)
            .filter(
                (field) =>
                    field.store &&
                    !["one2many", "many2many", "binary"].includes(field.type),
            )
            .map((field) => ({
                label: `${field.string} (${field.name})`,
                value: field.name,
            }));
    }

    get defaultGroupbyChoices() {
        return fieldsToChoices(
            this.viewEditorModel.fields,
            this.viewEditorModel.GROUPABLE_TYPES,
            (field) => field.store,
        );
    }

    /**
     * @param {Array<Number>} resIds
     */
    changeAdditionalFields(resIds) {
        const currentFullIds = this.currentAdditionalFieldsIds;
        const newIds = resIds.filter((id) => !currentFullIds.includes(id));
        let toRemoveIds;

        const operationType = newIds.length ? "add" : "remove";

        if (operationType === "remove") {
            toRemoveIds = currentFullIds.filter((id) => !resIds.includes(id));
        }

        this.viewEditorModel.doOperation({
            type: "map_popup_fields",
            target: {
                operation_type: operationType,
                field_ids: operationType === "add" ? newIds : toRemoveIds,
            },
        });
    }

    editDefaultGroupBy(value) {
        this.editArchAttributes({ default_group_by: value.join(",") });
    }
}

registry.category("studio_editors").add("map", {
    label: _t("Map"),
    icon: "fa-solid fa-location-dot",
    group: "multiple",
    newViewDialog: MapNewViewDialog,
    ...mapView,
    Sidebar: MapEditorSidebar,
});
