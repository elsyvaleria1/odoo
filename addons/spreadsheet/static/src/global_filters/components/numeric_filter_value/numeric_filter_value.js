/** @odoo-module native */
/** @ts-check */

import { Component, t, useProps } from "@odoo/owl";
import { parseFloat } from "@web/core/parsers";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useNumpadDecimal } from "@web/fields/numpad_decimal_hook";

export class NumericFilterValue extends Component {
    static template = "spreadsheet.NumericFilterValue";
    static props = {
        onValueChanged: t.function(),
        value: t.or([t.number(), t.string()]).optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.inputRef = elementRef();
        useNumpadDecimal(this.inputRef);
        useLayoutEffect(
            (el, value) => {
                if (!el || el === document.activeElement) {
                    return;
                }
                const text = value ?? "";
                if (el.value !== String(text)) {
                    el.value = text;
                }
            },
            () => [this.inputRef.el, this.props.value],
        );
    }

    onChange(value) {
        let numericValue;
        if (value === undefined || value === "") {
            numericValue = undefined;
        } else {
            try {
                numericValue = parseFloat(value);
                // eslint-disable-next-line no-unused-vars
            } catch (e) {
                numericValue = 0;
            }
        }
        this.props.onValueChanged(numericValue);
        if (numericValue === 0 && this.inputRef?.el) {
            this.inputRef.el.value = 0;
        }
    }
}
