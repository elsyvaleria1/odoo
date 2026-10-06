// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { TagsList } from "@web/components/tags_list/tags_list";
import { IN_RANGE_OPTIONS } from "@web/core/tree/in_range_options";
import {
    matchInRangeProviderOption,
    resolveInRangeProviderOption,
} from "@web/core/tree/in_range_providers";
import { elementRef } from "@web/core/utils/element_ref";
export class Input extends Component {
    static props = {
        value: t.any(),
        update: t.function(),
        placeholder: t.string().optional(),
        startEmpty: t.boolean().optional(),
    };
    static template = "web.TreeEditor.Input";
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref<HTMLInputElement>} */
    inputRef;

    setup() {
        this.inputRef = elementRef();
    }

    /** @param {Event} ev */
    async onChange(ev) {
        const el = /** @type {HTMLInputElement} */ (ev.target);
        await this.props.update(el.value);
        const input = /** @type {HTMLInputElement | null} */ (this.inputRef.el);
        if (!this.props.startEmpty && input) {
            input.value = this.props.value;
        }
    }
}

export class Select extends Component {
    static props = {
        value: t.any(),
        update: t.function(),
        options: t.array(),
        placeholder: t.string().optional(),
        addBlankOption: t.boolean().optional(),
        optionGroups: t.object().optional(),
    };
    static template = "web.TreeEditor.Select";
    props = useProps(this.constructor.props);

    /** @returns {{ungrouped: any[], groups: Array<[string, any[]]>}} */
    get renderedOptions() {
        const groups = new Map();
        const ungrouped = [];
        for (const option of this.props.options) {
            const group = this.props.optionGroups?.[this.serialize(option[0])];
            if (!group) {
                ungrouped.push(option);
                continue;
            }
            if (!groups.has(group)) {
                groups.set(group, []);
            }
            groups.get(group).push(option);
        }
        return { ungrouped, groups: [...groups] };
    }

    /**
     * @param {string} value
     * @returns {any}
     */
    deserialize(value) {
        return JSON.parse(value);
    }

    /**
     * @param {any} value
     * @returns {string}
     */
    serialize(value) {
        return JSON.stringify(value);
    }
}

export class Range extends Component {
    static props = { value: t.array(), update: t.function(), editorInfo: t.object() };
    static template = "web.TreeEditor.Range";
    props = useProps(this.constructor.props);

    /**
     * @param {0|1} index
     * @param {any} newValue
     */
    update(index, newValue) {
        const result = [...this.props.value];
        result[index] = newValue;
        return this.props.update(result);
    }
}

export class InRange extends Component {
    static props = {
        value: t.array(),
        update: t.function(),
        valueTypeEditorInfo: t.object(),
        betweenEditorInfo: t.object(),
    };
    static template = "web.TreeEditor.InRange";
    static options = IN_RANGE_OPTIONS;
    props = useProps(this.constructor.props);

    /** @returns {string} */
    get selectedValueType() {
        const [fieldType, valueType, start, end] = this.props.value;
        if (valueType !== "custom range") {
            return valueType;
        }
        return matchInRangeProviderOption(fieldType, start, end) || valueType;
    }

    /** @param {string} newValueType */
    updateValueType(newValueType) {
        const [fieldType] = this.props.value;
        if (newValueType === this.selectedValueType) {
            return;
        }
        const bounds = resolveInRangeProviderOption(newValueType, fieldType);
        if (bounds) {
            return this.props.update([fieldType, "custom range", ...bounds]);
        }
        const values =
            newValueType === "custom range"
                ? this.props.betweenEditorInfo.defaultValue()
                : [false, false];
        return this.props.update([fieldType, newValueType, ...values]);
    }
    /** @param {[any, any]} values */
    updateValues(values) {
        const [fieldType, currentValueType] = this.props.value;
        return this.props.update([fieldType, currentValueType, ...values]);
    }
}

export class List extends Component {
    static components = { TagsList };
    static props = { value: t.array(), update: t.function(), editorInfo: t.object() };
    static template = "web.TreeEditor.List";
    props = useProps(this.constructor.props);

    /** @returns {Array<{text: string, colorIndex: number, onDelete: Function}>} */
    get tags() {
        const { isSupported, stringify } = this.props.editorInfo;
        return this.props.value.map(
            (/** @type {any} */ val, /** @type {number} */ index) => ({
                text: stringify(val),
                colorIndex: isSupported(val) ? 0 : 2,
                onDelete: () => {
                    this.props.update([
                        ...this.props.value.slice(0, index),
                        ...this.props.value.slice(index + 1),
                    ]);
                },
            }),
        );
    }

    /** @param {any} newValue */
    update(newValue) {
        return this.props.update([...this.props.value, newValue]);
    }
}
