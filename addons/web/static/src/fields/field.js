// @ts-check
/** @odoo-module native */

import { Component, computed, t, useProps, xml } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { Domain } from "@web/core/domain";
import { evaluateBooleanExpr, evaluateExpr } from "@web/core/py_js/py";
import { registry } from "@web/core/registry";
import { fieldLog } from "@web/core/utils/asset_log";
import { omit } from "@web/core/utils/collections/objects";
import { getClassNameFromDecoration } from "@web/core/utils/decorations";
import { useRenderCounter } from "@web/core/utils/render_instrumentation";
import { getFieldContext } from "@web/model/relational_model";
import {
    FIELD_DEPENDENCIES_VALIDATION,
    RELATED_FIELDS_VALIDATION,
} from "@web/model/relational_model/field_metadata";

import { getTooltipInfo } from "./field_tooltip.js";
import { standardFieldProps } from "./standard_field_props.js";

const fieldRegistry = registry.category("fields");

const validFieldTypes = [
    "binary",
    "boolean",
    "json",
    "integer",
    "float",
    "monetary",
    "properties",
    "properties_definition",
    "reference",
    "many2one_reference",
    "many2one",
    "one2many",
    "many2many",
    "selection",
    "date",
    "datetime",
    "char",
    "text",
    "html",
];

const supportedInfoEntryShape = {
    name: t.string(),
    label: t.string().optional(),
    type: t.string().optional(),
    availableTypes: t.array(t.string()).optional(),
    default: t.any().optional(),
    help: t.string().optional(),
    choices: t
        .array(t.object({ label: t.string().optional(), value: t.any().optional() }))
        .optional(),
    isRelationalField: t.boolean().optional(),
    placeholder: t.string().optional(),
};

const supportedInfoValidation = t
    .array(
        t.or([
            t.object(supportedInfoEntryShape),
            t.array(t.object(supportedInfoEntryShape)),
        ]),
    )
    .optional();

fieldRegistry.addValidation(
    t.strictObject({
        component: t.customValidator(
            t.any(),
            (/** @type {any} */ c) => c.prototype instanceof Component,
        ),
        displayName: t.string().optional(),
        supportedAttributes: supportedInfoValidation,
        supportedOptions: supportedInfoValidation,
        supportedTypes: t
            .customValidator(t.array(t.string()), (/** @type {any} */ array) =>
                array.every((/** @type {any} */ x) => validFieldTypes.includes(x)),
            )
            .optional(),
        extractProps: t.function().optional(),
        isEmpty: t.function().optional(),
        isValid: t.function().optional(),
        additionalClasses: t.array(t.string()).optional(),
        fieldDependencies: FIELD_DEPENDENCIES_VALIDATION,
        relatedFields: RELATED_FIELDS_VALIDATION,
        useSubView: t.boolean().optional(),
        interactiveOutsideEdition: t.or([t.boolean(), t.function()]).optional(),
        label: t.or([t.string(), t.literal(false)]).optional(),
        listViewWidth: t
            .or([
                t.number(),
                t.literal("content"),
                t.customValidator(
                    t.array(t.number()),
                    (/** @type {any} */ array) =>
                        array.length === 1 || array.length === 2,
                ),
                t.function(),
            ])
            .optional(),
    }),
);

class DefaultField extends Component {
    static template = xml``;
    static props = null;
    props = useProps(this.constructor.props);
}

/** @type {WeakMap<Function, Function>} */
const COUNTED_COMPONENTS = new WeakMap();

/**
 * @param {any} C
 * @returns {any}
 */
function countedComponent(C) {
    let counted = COUNTED_COMPONENTS.get(C);
    if (!counted) {
        counted = class extends C {
            setup() {
                useRenderCounter(`fields.${C.template}`);
                super.setup?.();
            }
        };
        Object.defineProperty(counted, "name", { value: C.name });
        COUNTED_COMPONENTS.set(C, counted);
    }
    return counted;
}

/** @type {readonly string[]} */
const FIELD_OWN_PROPS = Object.freeze([
    "attrs",
    "class",
    "fieldInfo",
    "readonly",
    "showTooltip",
    "style",
    "type",
]);

/** @type {Set<string>} */
const warnedWidgetMisses = new Set();

const log = makeLogger("web.field");

export function resetWidgetMissWarnings() {
    warnedWidgetMisses.clear();
}

/**
 * @param {{ supportedOptions?: any[], [key: string]: any }} field
 * @returns {Set<string> | null}
 */
export function getSupportedOptionNames(field) {
    if (!field?.supportedOptions) {
        return null;
    }
    const names = new Set();
    for (const entry of field.supportedOptions) {
        for (const descriptor of Array.isArray(entry) ? entry : [entry]) {
            if (descriptor?.name) {
                names.add(descriptor.name);
            }
        }
    }
    return names;
}

/**
 * @param {string} fieldType
 * @param {string} [widget]
 * @param {string} [viewType]
 * @param {string} [jsClass]
 * @returns {{ component: import("@odoo/owl").ComponentConstructor, extractProps?: Function, supportedTypes?: string[], isEmpty?: Function, isValid?: Function, additionalClasses?: string[], relatedFields?: Array | Function, useSubView?: boolean, [key: string]: any }}
 */
export function getFieldFromRegistry(fieldType, widget, viewType, jsClass) {
    fieldLog("resolve", widget || fieldType, viewType || "", jsClass || "");
    const prefixes = jsClass ? [jsClass, viewType, ""] : [viewType, ""];
    /** @param {string} key */
    const findInRegistry = (key) => {
        for (const prefix of prefixes) {
            const field = fieldRegistry.get(
                prefix ? `${prefix}.${key}` : key,
                undefined,
            );
            if (field) {
                return field;
            }
        }
    };
    if (widget) {
        const field = findInRegistry(widget);
        const warningKey = `${widget}|${fieldType}`;
        if (field) {
            if (
                field.supportedTypes &&
                !field.supportedTypes.includes(fieldType) &&
                !warnedWidgetMisses.has(warningKey)
            ) {
                warnedWidgetMisses.add(warningKey);
                console.warn(
                    `The widget: ${widget} don't support the type ${fieldType}`,
                );
            }
            return field;
        }
        if (!warnedWidgetMisses.has(warningKey)) {
            warnedWidgetMisses.add(warningKey);
            console.warn(`Missing widget: ${widget} for field of type ${fieldType}`);
        }
    }
    return (
        /** @type {any} */ (findInRegistry(fieldType) || { component: DefaultField })
    );
}

/**
 * @param {{ isEmpty?: (record: any, fieldName: string) => boolean, isValid?: (record: any, fieldName: string, fieldInfo: any) => boolean }} field
 * @param {import("@web/model/relational_model/record").RelationalRecord} record
 * @param {string} fieldName
 * @param {{ readonly?: string } & Record<string, any>} fieldInfo
 * @returns {{ readonly: boolean, invalid: boolean, empty: boolean }}
 */
export function fieldLabelFeedback(field, record, fieldName, fieldInfo) {
    const readonly = evaluateBooleanExpr(
        fieldInfo.readonly,
        record.evalContextWithVirtualIds,
    );
    const inEdit = record.isInEdition;

    let empty = !record.isNew;
    empty =
        empty &&
        (field.isEmpty ? field.isEmpty(record, fieldName) : !record.data[fieldName]);
    empty = inEdit ? empty && readonly : empty;
    return {
        readonly,
        invalid: field.isValid
            ? !field.isValid(record, fieldName, fieldInfo)
            : record.isFieldInvalid(fieldName),
        empty,
    };
}

/**
 * @param {Parameters<typeof fieldLabelFeedback>[0]} field
 * @param {import("@web/model/relational_model/record").RelationalRecord} record
 * @param {string} fieldName
 * @param {{ readonly?: string, required?: string }} fieldInfo
 * @returns {{ readonly: boolean, required: boolean, invalid: boolean, empty: boolean }}
 */
export function fieldVisualFeedback(field, record, fieldName, fieldInfo) {
    return {
        ...fieldLabelFeedback(field, record, fieldName, fieldInfo),
        required: evaluateBooleanExpr(
            fieldInfo.required,
            record.evalContextWithVirtualIds,
        ),
    };
}

/**
 * @param {{ readonly: boolean, required: boolean, invalid: boolean, empty: boolean }} previous
 * @param {{ readonly: boolean, required: boolean, invalid: boolean, empty: boolean }} next
 * @returns {boolean}
 */
function sameVisualFeedback(previous, next) {
    return (
        previous.readonly === next.readonly &&
        previous.required === next.required &&
        previous.invalid === next.invalid &&
        previous.empty === next.empty
    );
}

/**
 * @param {{ name: string, type: string, widget?: string, string?: string, relation?: string, domain?: string, selection?: Array, tags?: Array, relatedPropertyField?: any }} propertyField
 * @param {string} [viewType]
 * @returns {{ name: string, type: string, viewType?: string, widget: string, string?: string, field: ReturnType<typeof getFieldFromRegistry>, options: Object, readonly: string, required: string, invisible: string, column_invisible: string, context: string, attrs: Object, decorations: Object, [key: string]: any }}
 */
export function getPropertyFieldInfo(propertyField, viewType) {
    const { name, relatedPropertyField, string, type, widget } = propertyField;

    /** @type {any} */
    const fieldInfo = {
        name,
        string,
        type,
        viewType,
        widget: widget || type,
        options: {},
        column_invisible: "False",
        invisible: "False",
        readonly: "False",
        required: "False",
        attrs: {},
        relatedPropertyField,

        context: "{}",
        help: undefined,
        onChange: false,
        forceSave: false,
        decorations: {},
        domain: undefined,
    };

    if (type === "many2one" || type === "many2many") {
        const { domain, relation } = propertyField;
        fieldInfo.relation = relation;
        fieldInfo.domain = domain;

        if (relation === "res.users" || relation === "res.partner") {
            fieldInfo.widget =
                propertyField.type === "many2one"
                    ? "many2one_avatar"
                    : "many2many_tags_avatar";
        } else {
            fieldInfo.widget =
                propertyField.type === "many2one" ? type : "many2many_tags";
        }
    } else if (type === "tags") {
        fieldInfo.tags = propertyField.tags;
        fieldInfo.widget = `property_tags`;
    } else if (type === "selection") {
        fieldInfo.selection = propertyField.selection;
    }

    fieldInfo.field = getFieldFromRegistry(
        propertyField.type,
        fieldInfo.widget,
        viewType,
    );
    let { relatedFields } = fieldInfo.field;
    if (relatedFields) {
        if (relatedFields instanceof Function) {
            relatedFields = relatedFields({ options: {}, attrs: {} });
        }
        fieldInfo.relatedFields = Object.fromEntries(
            relatedFields.map((/** @type {any} */ f) => [f.name, f]),
        );
    }

    return fieldInfo;
}
const archString = t.or([t.string(), t.literal(null)]).optional();

export const fieldProps = {
    ...standardFieldProps,
    attrs: t.object().optional(),
    class: archString,
    fieldInfo: t.object().optional(),
    showTooltip: t.boolean().optional(),
    style: archString,
    type: archString,
};

export class Field extends Component {
    static template = "web.Field";
    static props = null;
    props = useProps(this.constructor.props);

    /** @type {(record?: any) => any[] | undefined} */
    dynamicDomain;

    setup() {
        if (this.props.fieldInfo) {
            this.field = this.props.fieldInfo.field;
        } else {
            const fieldType = this.props.record.fields[this.props.name].type;
            this.field = getFieldFromRegistry(fieldType, this.props.type);
        }
        log.lifecycle("setup", () => ({
            name: this.props.name,
            widget: this.props.type,
            component: this.field?.component?.name,
            resModel: this.props.record.resModel,
        }));
        this.dynamicDomain = (record = this.props.record) => {
            const { fieldInfo } = this.props;
            if (fieldInfo?.domain) {
                return new Domain(
                    evaluateExpr(fieldInfo.domain, record.evalContext),
                ).toList();
            }
        };
        this.visualFeedback = computed(
            () => {
                const feedback = fieldVisualFeedback(
                    this.field,
                    this.props.record,
                    this.props.name,
                    this.props.fieldInfo || {},
                );
                log.logic("visualFeedback", () => ({
                    name: this.props.name,
                    ...feedback,
                }));
                return feedback;
            },
            { equals: sameVisualFeedback },
        );
        this.computedTooltip = computed(() => {
            const tooltip = this.computeTooltip();
            log.logic("tooltip", () => ({
                name: this.props.name,
                shown: Boolean(tooltip),
            }));
            return tooltip;
        });
    }

    /** @returns {Record<string, boolean>} */
    get classNames() {
        const { class: _class, fieldInfo, record } = this.props;
        const { readonly, required, invalid, empty } = this.visualFeedback();
        const classNames = {
            o_field_widget: true,
            o_readonly_modifier: readonly,
            o_required_modifier: required,
            o_field_invalid: invalid,
            o_field_empty: empty,
            [`o_field_${this.type}`]: true,
            ...(_class ? { [_class]: true } : {}),
        };
        if (this.field.additionalClasses) {
            for (const cls of this.field.additionalClasses) {
                classNames[cls] = true;
            }
        }

        if (fieldInfo?.decorations) {
            const { decorations } = fieldInfo;
            for (const decoName of Object.keys(decorations)) {
                const value = evaluateBooleanExpr(
                    decorations[decoName],
                    record.evalContextWithVirtualIds,
                );
                classNames[getClassNameFromDecoration(decoName)] = value;
            }
        }

        return classNames;
    }

    /** @returns {string} */
    get type() {
        return this.props.type || this.props.record.fields[this.props.name].type;
    }

    /** @returns {import("@odoo/owl").ComponentConstructor} */
    get fieldComponent() {
        return countedComponent(this.field.component);
    }

    /** @returns {Object} */
    get fieldComponentProps() {
        const record = this.props.record;
        let readonly = this.props.readonly || false;

        let propsFromNode = {};
        if (this.props.fieldInfo) {
            let fieldInfo = this.props.fieldInfo;
            readonly = readonly || this.visualFeedback().readonly;

            if (this.field.extractProps) {
                if (this.props.attrs) {
                    fieldInfo = {
                        ...fieldInfo,
                        attrs: { ...fieldInfo.attrs, ...this.props.attrs },
                    };
                }
                if (
                    fieldInfo.attrs.placeholder ||
                    fieldInfo.options.placeholder_field
                ) {
                    fieldInfo = {
                        ...fieldInfo,
                        placeholder:
                            record.data[fieldInfo.options.placeholder_field] ||
                            fieldInfo.attrs.placeholder,
                    };
                }

                const contextOwner = this;
                const dynamicInfo = {
                    get context() {
                        return getFieldContext(
                            record,
                            fieldInfo.name,
                            fieldInfo.context,
                            contextOwner,
                        );
                    },
                    domain: this.dynamicDomain,
                    required: this.visualFeedback().required,
                    readonly: readonly,
                };
                propsFromNode = this.field.extractProps(fieldInfo, dynamicInfo);
            }
        }

        const props = omit(this.props, ...FIELD_OWN_PROPS);

        const { interactiveOutsideEdition } = this.field;
        const inEditionOnly = !(typeof interactiveOutsideEdition === "function"
            ? interactiveOutsideEdition(this.props.fieldInfo || {})
            : interactiveOutsideEdition);

        return {
            readonly: (inEditionOnly && !record.isInEdition) || readonly,
            ...propsFromNode,
            ...props,
        };
    }

    /** @returns {string | false} */
    computeTooltip() {
        if (!this.props.showTooltip) {
            return false;
        }
        const field = this.props.record.fields[this.props.name];
        const fieldInfo = this.props.fieldInfo || {};
        if (!odoo.debug && !(fieldInfo.help ?? field.help)) {
            return false;
        }
        return getTooltipInfo({ field, fieldInfo });
    }

    /** @returns {string | false} */
    get tooltip() {
        return this.computedTooltip();
    }
}
