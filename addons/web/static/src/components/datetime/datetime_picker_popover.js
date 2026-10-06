// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";

import { DateTimePicker } from "./datetime_picker.js";

/** @import { DateTimePickerProps } from "./datetime_picker.js" */

/**
 * @typedef DateTimePickerPopoverProps
 * @property {() => void} close
 * @property {DateTimePickerProps} pickerProps
 */

/** @extends {Component<DateTimePickerPopoverProps>} */
export class DateTimePickerPopover extends Component {
    static components = { DateTimePicker };

    static props = { close: t.function(), pickerProps: t.object(DateTimePicker.props) };

    static template = "web.DateTimePickerPopover";
    props = useProps(this.constructor.props);

    setup() {
        useHotkey("enter", () => this.props.close());
    }
}
