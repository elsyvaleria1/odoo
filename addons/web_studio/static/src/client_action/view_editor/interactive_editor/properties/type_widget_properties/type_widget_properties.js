/** @odoo-module native */
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import {
    fieldsToChoices,
    getWowlFieldWidgets,
} from "@web_studio/client_action/view_editor/editors/utils";
import {
    COMPUTED_DISPLAY_OPTIONS,
    FIELD_TYPE_ATTRIBUTES,
} from "@web_studio/client_action/view_editor/interactive_editor/properties/type_widget_properties/type_specific_and_computed_properties";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class TypeWidgetProperties extends Component {
    static template =
        "web_studio.ViewEditor.InteractiveEditorProperties.Field.TypeWidgetProperties";
    static components = { Property };
    static props = { node: t.object(), onChangeAttribute: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.debug = useDebugMode();
        this.orm = useService("orm");
        this.fieldService = useService("field");
        this.attributes = proxy({
            field: [],
            selection: [],
            boolean: [],
            domain: [],
            number: [],
            string: [],
            digits: [],
        });

        onWillStart(async () => {
            await this.computeAttributesList(this.props);
        });

        onWillUpdateProps(async (nextProps) => {
            await this.computeAttributesList(nextProps);
        });
    }

    async computeAttributesList(props) {
        this.attributesForCurrentTypeAndWidget =
            this.getAttributesForCurrentTypeAndWidget(props);
        await this.groupAttributesPerType(props);
    }

    async groupAttributesPerType(props) {
        this.attributes.field = await this.getAttributesOfTypeField(props);
        this.attributes.selection = this.getWidgetAttributes("selection", props);
        this.attributes.boolean = this.getWidgetAttributes("boolean", props);
        this.attributes.domain = this.getWidgetAttributes("domain", props);
        this.attributes.number = this.getWidgetAttributes("number", props);
        this.attributes.string = this.getWidgetAttributes("string", props);
        this.attributes.digits = this.getWidgetAttributes("digits", props);
    }

    async getAttributesOfTypeField(props) {
        const fieldAttributes = this.getWidgetAttributes("field", props);
        if (fieldAttributes.length) {
            const fields = Object.entries(this.viewEditorModel.fields).map(
                ([key, value]) => ({
                    ...value,
                    name: value.name || key,
                }),
            );
            await Promise.all(
                fieldAttributes.map(async (attribute) => {
                    const choices = await this.getFieldChoices(attribute, fields);
                    if (
                        this.props.node.field?.type === "monetary" &&
                        attribute.name === "currency_field"
                    ) {
                        attribute.isRequired = true;
                    }
                    attribute.choices = choices;
                    this.getOptionObj(attribute.name).choices = choices;
                }),
            );
            return fieldAttributes;
        }
        return [];
    }

    getSupportedOptionsAndAttributes(props) {
        const widgetName = this.isField
            ? props.node.attrs?.widget || props.node.field?.type
            : props.node.attrs.name;
        const itemsRegistry = registry.category(
            this.isField ? "fields" : "view_widgets",
        ).content;
        const widgetDescription =
            itemsRegistry[this.viewEditorModel.viewType + "." + widgetName] ||
            itemsRegistry[widgetName];
        const options = widgetDescription?.[1].supportedOptions || [];
        const optionNames = new Set(options.map((option) => option.name));
        return [
            ...(widgetDescription?.[1].supportedAttributes || [])
                .filter((attribute) => !optionNames.has(attribute.name))
                .map((e) => ({
                    ...e,
                    isAttribute: true,
                })),
            ...options,
        ];
    }

    /**
     * @returns {{choices: Object[]}} the available widgets for the current node
     */
    get widgetChoices() {
        const widgets = getWowlFieldWidgets(
            this.props.node.field.type,
            this.props.node.attrs.widget,
            [],
            this.debug,
        );
        return {
            choices: widgets.map(([value, label]) => {
                label = label ? label : "";
                return {
                    label: `${label} (${value})`.trim(),
                    value,
                };
            }),
        };
    }

    /**
     * @returns the list of attributes available depending the type of field,
     * as well the current widget selected. For a widget node, there is no
     * concept of type, we simply read what supported options and attributes
     * are on the node
     */
    _getAttributesForCurrentTypeAndWidget(props) {
        if (!props.node.field) {
            return JSON.parse(
                JSON.stringify(this.getSupportedOptionsAndAttributes(props)),
            );
        }

        this.isField = true;

        const fieldType = props.node.field.type;
        const { viewType } = this.viewEditorModel;

        const fieldCommonViewsProperties =
            FIELD_TYPE_ATTRIBUTES[fieldType]?.common || [];
        const fieldSpecificViewProperties =
            FIELD_TYPE_ATTRIBUTES[fieldType]?.[viewType] || [];
        const widgetProperties = JSON.parse(
            JSON.stringify(this.getSupportedOptionsAndAttributes(props)),
        );
        const widgetPropertyNames = new Set(widgetProperties.map((p) => p.name));

        return [
            ...[...fieldCommonViewsProperties, ...fieldSpecificViewProperties]
                .filter((property) => !widgetPropertyNames.has(property.name))
                .map((e) => ({ ...e, isAttribute: true })),
            ...widgetProperties,
        ];
    }

    getAttributesForCurrentTypeAndWidget(props) {
        const _attributes = this._getAttributesForCurrentTypeAndWidget(props);
        _attributes.forEach((property) => {
            if (COMPUTED_DISPLAY_OPTIONS[property.name]) {
                const dependentOption = COMPUTED_DISPLAY_OPTIONS[property.name];
                const superOption = _attributes.find(
                    (o) => o.name === dependentOption.superOption,
                );
                property.isSubOption = true;
                if (!superOption.subOptions) {
                    superOption.subOptions = [];
                }
                if (!superOption.subOptions.includes(property.name)) {
                    superOption.subOptions.push(property.name);
                }
            }
        });
        return _attributes;
    }

    getOptionObj(optionName) {
        return this.attributesForCurrentTypeAndWidget.find(
            (o) => o.name === optionName,
        );
    }

    isAttributeReadonly(attribute) {
        if ("isReadonly" in attribute) {
            return attribute.isReadonly;
        }
        if (
            this.props.node.field?.type === "monetary" &&
            attribute.name === "currency_field"
        ) {
            return !this.props.node.field.manual;
        }
    }

    /**
     * @param {string} type of the attribute (eg. "string", "boolean" )
     * @returns only the given type of attributes for the current field node
     */
    getWidgetAttributes(type, props) {
        return this.attributesForCurrentTypeAndWidget
            .filter((attribute) => attribute.type === type)
            .map((attribute) => {
                if (attribute.isAttribute) {
                    return this.getPropertyFromAttributes(attribute, props);
                }
                return this.getPropertyFromOptions(attribute, props);
            })
            .filter((attribute) => attribute !== undefined);
    }

    async getFieldChoices(attribute, fields) {
        let availableFields = fields;
        if (
            attribute.isRelationalField &&
            this.props.node.field.relation !== this.viewEditorModel.resModel
        ) {
            const newFields = await this.fieldService.loadFields(
                this.props.node.field.relation,
            );
            availableFields = Object.entries(newFields).map(([key, value]) => ({
                ...value,
                name: value.name || key,
            }));
        }
        if (attribute.name === "fold_field") {
            if (this.viewEditorModel.activeNode.field.type === "selection") {
                attribute.isInvisible = true;
                return [];
            }
            const fields = await this.orm.call(
                this.viewEditorModel.activeNode.field.relation,
                "fields_get",
            );
            availableFields = Object.values(fields);
        } else if (attribute.name === "currency_field") {
            availableFields = availableFields.filter(
                (f) => f.relation === "res.currency",
            );
        }
        return fieldsToChoices(
            availableFields,
            attribute.availableTypes,
            (f) => f.name !== this.viewEditorModel.activeNode.attrs.name,
        );
    }

    getPropertyFromAttributes(property, props) {
        let value;
        value = props.node.attrs[property.name];
        if (property.getValue) {
            const attrs = props.node.attrs || {};
            const field = props.node.field || {};
            value = property.getValue({ attrs, field });
        }
        if (value === undefined && property.default) {
            value = property.default;
        }
        return {
            ...property,
            value,
        };
    }

    getPropertyFromOptions(property, props) {
        let value;
        if (COMPUTED_DISPLAY_OPTIONS[property.name]) {
            const dependentOption = COMPUTED_DISPLAY_OPTIONS[property.name];
            const superOption = this.getOptionObj(dependentOption.superOption);
            const superValue = this.getPropertyFromOptions(superOption, props).value;
            if (dependentOption.getReadonly) {
                property.isReadonly = dependentOption.getReadonly(superValue);
            }
            if (dependentOption.getValue) {
                property.value = dependentOption.getValue(superValue);
                if (property.isReadonly) {
                    return property;
                }
            }
            if (dependentOption.getInvisible) {
                property.isInvisible = dependentOption.getInvisible(superValue);
            }
        }
        value = props.node.attrs.options?.[property.name];
        if (property.type === "string" && value && typeof value !== "string") {
            value = JSON.stringify(value);
        }
        if (property.type === "boolean" && value !== undefined) {
            value = !!value;
        }
        if (value === undefined && property.default) {
            value = property.default;
        }
        if (property.name === "currency_field" && !value) {
            value = props.node.field.currency_field;
        }
        return {
            ...property,
            value,
        };
    }

    getSelectValue(value) {
        return typeof value === "object" ? JSON.stringify(value) : value;
    }

    async onChangeCurrency(value) {
        const proms = [];
        if (this.props.node.field.manual) {
            proms.push(
                rpc("/web_studio/set_currency", {
                    model_name: this.viewEditorModel.resModel,
                    field_name: this.props.node.field.name,
                    value,
                }),
            );
        } else {
            proms.push(Promise.resolve(false));
        }

        if (this.viewEditorModel.fieldsInArch.includes(value)) {
            const [currencyChanged] = await Promise.all(proms);
            if (currencyChanged) {
                this.viewEditorModel.fields[this.props.node.field.name][
                    "currency_field"
                ] = value;
                this.attributes.field = this.attributes.field.map((e) => {
                    if (e.name === "currency_field") {
                        e.value = value;
                    }
                    return e;
                });
            }
            return;
        }

        const currencyNode = {
            tag: "field",
            attrs: { name: value },
        };

        const operation = {
            node: currencyNode,
            target: this.viewEditorModel.getFullTarget(
                this.viewEditorModel.activeNodeXpath,
            ),
            position: "after",
            type: "add",
        };

        proms.push(this.viewEditorModel.doOperation(operation));
        const [currencyChanged] = await Promise.all(proms);
        if (currencyChanged) {
            this.viewEditorModel.fields[this.props.node.field.name]["currency_field"] =
                value;
        }
    }

    onChangeWidget(value) {
        return this.props.onChangeAttribute(value, "widget");
    }

    async onChangeProperty(value, name) {
        if (
            ["show_seconds", "show_time"].includes(name) &&
            !value &&
            this.props.node.field.type === "datetime" &&
            !this.props.node.attrs.widget
        ) {
            this.onChangeWidget("datetime");
        } else if (
            name === "currency_field" &&
            this.props.node.field.type === "monetary"
        ) {
            await this.onChangeCurrency(value);
            if (!this.props.node.attrs.options?.[name]) {
                return;
            }
            value = "";
        }

        const currentProperty = this.getOptionObj(name);
        if (currentProperty.isAttribute) {
            return this.props.onChangeAttribute(value, name);
        }
        const options = { ...this.props.node.attrs.options };
        if (value || currentProperty.type === "boolean") {
            if (currentProperty.type === "digits") {
                value = Number(value);
                if (!Number.isInteger(value) || value < 0 || value > 20) {
                    return;
                }
                options[name] = [value * 2, value];
            } else if (["[", "{"].includes(value[0]) || !isNaN(value)) {
                options[name] = JSON.parse(value);
            } else if (currentProperty.type === "number") {
                options[name] = Number(value);
            } else {
                options[name] = value;
            }
        } else {
            delete options[name];
        }
        this.props.onChangeAttribute(JSON.stringify(options), "options");
    }
}
