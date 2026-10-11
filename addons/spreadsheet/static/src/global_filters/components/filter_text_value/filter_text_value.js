/** @odoo-module native */
/** @ts-check */

import { Component, t, useProps } from "@odoo/owl";
import { AutoComplete } from "@web/components/autocomplete";
import { TagsList } from "@web/components/tags_list";
import { useChildRef } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class TextFilterValue extends Component {
    static template = "spreadsheet.TextFilterValue";
    static components = {
        TagsList,
        AutoComplete,
    };
    static props = {
        onValueChanged: t.function(),
        value: t.array().optional([]),
        options: t.array(
            t.object({ value: t.string(), formattedValue: t.string() }).optional(),
        ),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.inputRef = useChildRef();
        useLayoutEffect(
            () => {
                if (this.props.options.length && this.inputRef.el) {
                    this.inputRef.el.setAttribute("maxlength", 0);
                } else {
                    this.inputRef.el.removeAttribute("maxlength");
                }
            },
            () => [this.props.options.length, this.inputRef.el],
        );
    }

    get tags() {
        return this.props.value.map((value) => ({
            id: value,
            text:
                this.props.options.find((option) => option.value === value)
                    ?.formattedValue ?? value,
            onDelete: () => {
                this.props.onValueChanged(this.props.value.filter((v) => v !== value));
            },
        }));
    }

    get sources() {
        const alreadySelected = new Set(this.props.value);
        return [
            {
                options: this.props.options
                    .filter((option) => !alreadySelected.has(option.value))
                    .map((option) => ({
                        label: option.formattedValue,
                        onSelect: () =>
                            this.props.onValueChanged([
                                ...this.props.value,
                                option.value,
                            ]),
                    })),
            },
        ];
    }

    onInputChange({ inputValue }) {
        const value = inputValue.trim();
        if (value) {
            if (!this.props.value?.includes(value)) {
                this.props.onValueChanged([...this.props.value, value]);
            }
            this.inputRef.el.value = "";
        }
    }
}
