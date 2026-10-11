/** @odoo-module native */
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    toRaw,
    useProps,
} from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";
import { SelectionContentDialog } from "@web_studio/client_action/view_editor/interactive_editor/field_configuration/selection_content_dialog";
import { TypeWidgetProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/type_widget_properties/type_widget_properties";
import { ViewStructureProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/view_structure_properties/view_structure_properties";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useEditNodeAttributes } from "@web_studio/client_action/view_editor/view_editor_model";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

import { ClassAttribute } from "../class_attribute/class_attribute.js";
import { ModifiersProperties } from "../modifiers/modifiers_properties.js";

class TechnicalName extends Component {
    static props = { node: t.object() };
    static template =
        "web_studio.ViewEditor.InteractiveEditorProperties.Field.TechnicalName";
    static components = { Property };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.debug = useDebugMode();
        this.renameField = (value) =>
            this.viewEditorModel.renameField(
                this.props.node.attrs.name,
                `x_studio_${value}`,
                {
                    autoUnique: false,
                },
            );
    }

    get canEdit() {
        return (
            this.debug &&
            this.viewEditorModel.isFieldRenameable(this.props.node.attrs.name)
        );
    }

    get fieldName() {
        const fName = this.props.node.attrs.name;
        if (this.canEdit) {
            return fName.split("x_studio_")[1];
        }
        return fName;
    }
}

export class FieldProperties extends Component {
    static template = "web_studio.ViewEditor.InteractiveEditorProperties.Field";
    static props = { node: t.object(), availableOptions: t.array().optional() };
    static components = {
        ClassAttribute,
        Property,
        TechnicalName,
        TypeWidgetProperties,
        ViewStructureProperties,
        ModifiersProperties,
    };
    props = useProps(this.constructor.props);

    setup() {
        this._viewEditorModel = useCurrentViewEditorModel();
        this.debug = useDebugMode();
        this.dialog = useService("dialog");
        this.multiCompany = user.allowedCompanies.length > 1;
        this.activeCompany = user.activeCompany;
        this.state = proxy({});
        this.editNodeAttributes = useEditNodeAttributes();

        onWillStart(async () => {
            if (this._canShowDefaultValue(this.props.node)) {
                this.state.defaultValue = await this.getDefaultValue(this.props.node);
            }
        });

        onWillUpdateProps(async (nextProps) => {
            if (this._canShowDefaultValue(nextProps.node)) {
                this.state.defaultValue = await this.getDefaultValue(nextProps.node);
            }
        });
    }

    get viewEditorModel() {
        return this._viewEditorModel;
    }

    async onChangeFieldString(value) {
        if (
            this.viewEditorModel.isFieldRenameable(this.props.node.field.name) &&
            value
        ) {
            return this.viewEditorModel.renameField(this.props.node.attrs.name, value, {
                label: value,
            });
        } else {
            const operation = {
                new_attrs: { string: value },
                type: "attributes",
                position: "attributes",
                target: this.viewEditorModel.getFullTarget(
                    this.viewEditorModel.activeNodeXpath,
                ),
            };
            operation.node = operation.target;
            return this.viewEditorModel.doOperation(operation);
        }
    }

    onChangeAttribute(value, name) {
        return this.editNodeAttributes({ [name]: value });
    }

    async onChangeDefaultValue(value) {
        await rpc("/web_studio/set_default_value", {
            model_name: this.viewEditorModel.resModel,
            field_name: this.props.node.field.name,
            value,
            company_id: user.activeCompany.id,
        });
        this.state.defaultValue = value;
    }

    getBoldValue() {
        const classList = this.props.node.arch.classList;
        return (
            classList.contains("fw-bold") ||
            classList.contains("fw-bolder") ||
            this.props.node.attrs.bold
        );
    }

    async getDefaultValue(node) {
        const defaultValueObj = await rpc("/web_studio/get_default_value", {
            model_name: this.viewEditorModel.resModel,
            field_name: node.field.name,
            company_id: user.activeCompany.id,
        });
        return defaultValueObj.default_value;
    }

    get optionalVisibilityChoices() {
        return {
            choices: [
                { label: _t("Show by default"), value: "show" },
                { label: _t("Hide by default"), value: "hide" },
            ],
        };
    }

    getDefaultValuePropertyProps() {
        if (!this._canShowDefaultValue(this.props.node)) {
            return null;
        }
        const { field, attrs } = this.props.node;
        const props = {
            childProps: {},
            inputAttributes: {},
        };
        if (field.selection) {
            props.childProps.choices = this.props.node.field.selection.map(
                ([value, label]) => ({
                    label,
                    value,
                }),
            );
        }
        const fieldType = field.type;
        const widget = attrs.widget;
        props.type = fieldType;
        if (widget === "statusbar") {
            props.type = "selection";
        }
        return props;
    }

    _canShowDefaultValue(node) {
        return !["image", "many2many", "one2many", "many2one", "binary"].includes(
            node.field.type,
        );
    }

    get canEditSelectionChoices() {
        return (
            this.props.node.field.manual && this.props.node.field.type === "selection"
        );
    }

    /**
     * @param {string} name of the attribute
     * @returns if this attribute supported in the current view
     */
    isAttributeSupported(name) {
        return this.props.availableOptions?.includes(name);
    }

    editSelectionChoices() {
        const field = this.props.node.field;
        this.dialog.add(SelectionContentDialog, {
            defaultChoices: toRaw(field).selection.map((s) => [...s]),
            onConfirm: async (choices) => {
                const result = await rpc("/web_studio/edit_field", {
                    model_name: this.viewEditorModel.resModel,
                    field_name: field.name,
                    values: { selection: JSON.stringify(choices) },
                    force_edit: false,
                });
                let reflectChanges = !result;
                if (result && result.records_linked) {
                    reflectChanges = false;
                    await new Promise((resolve) => {
                        this.dialog.add(ConfirmationDialog, {
                            body:
                                result.message ||
                                _t(
                                    "Are you sure you want to remove the selection values?",
                                ),
                            confirm: async () => {
                                await rpc("/web_studio/edit_field", {
                                    model_name: this.viewEditorModel.resModel,
                                    field_name: field.name,
                                    values: { selection: JSON.stringify(choices) },
                                    force_edit: true,
                                });
                                reflectChanges = true;
                                resolve();
                            },
                            cancel: () => resolve(),
                        });
                    });
                }
                if (reflectChanges) {
                    field.selection = choices;
                }
            },
        });
    }
}
