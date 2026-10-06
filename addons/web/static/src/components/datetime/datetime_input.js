// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { omit } from "@web/core/utils/collections/objects";
import { elementRef } from "@web/core/utils/element_ref";

import { DateTimePicker } from "./datetime_picker.js";
import { useDateTimePicker } from "./datetime_picker_hook.js";
/** @typedef {Temporal.ZonedDateTime} DateTime */

/**
 * @typedef {import("./datetime_picker").DateTimePickerProps & {
 * class?: string;
 * disabled?: boolean;
 * format?: string;
 * id?: string;
 * onApply?: (value: DateTime) => any;
 * onChange?: (value: DateTime) => any;
 * placeholder?: string;
 * }} DateTimeInputProps
 */

const dateTimeInputOwnProps = {
    format: t.string().optional(),
    id: t.string().optional(),
    class: t.string().optional(),
    onChange: t.function().optional(),
    onApply: t.function().optional(),
    placeholder: t.string().optional(),
    disabled: t.boolean().optional(),
};

const DATE_TIME_INPUT_OWN_PROP_NAMES = Object.keys(dateTimeInputOwnProps);

/** @extends {Component<DateTimeInputProps>} */
export class DateTimeInput extends Component {
    static props = { ...DateTimePicker.props, ...dateTimeInputOwnProps };

    static template = "web.DateTimeInput";
    props = useProps(this.constructor.props);

    setup() {
        const getPickerProps = () =>
            omit(this.props, .../** @type {any} */ (DATE_TIME_INPUT_OWN_PROP_NAMES));

        const component = this;
        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        useDateTimePicker(
            /** @type {any} */ ({
                endDateRef: this.endDateRef,
                startDateRef: this.startDateRef,
                get format() {
                    return component.props.format;
                },
                get showSeconds() {
                    return /** @type {number} */ (component.props.rounding) <= 0;
                },
                get pickerProps() {
                    return getPickerProps();
                },
                onApply: (/** @type {any} */ value) => this.props.onApply?.(value),
                onChange: (/** @type {any} */ value) => this.props.onChange?.(value),
            }),
        );
    }
}
