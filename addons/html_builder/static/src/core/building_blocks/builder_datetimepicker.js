/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useDateTimePicker } from "@web/components/datetime";
import {
    ConversionError,
    dateTime,
    formatDate,
    formatDateTime,
    fromEpochMilliseconds,
    now,
    parseDateTime,
    toDate,
} from "@web/core/l10n/dates";
import { pick } from "@web/core/utils/collections/objects";
import { elementRef } from "@web/core/utils/element_ref";
import { effect } from "@web/core/utils/reactive";

import {
    basicContainerBuilderComponentProps,
    useBuilderComponent,
    useInputBuilderComponent,
} from "../utils.js";
import { BuilderComponent } from "./builder_component.js";
import {
    BuilderTextInputBase,
    textInputBasePassthroughProps,
} from "./builder_text_input_base.js";

/** @param {Temporal.ZonedDateTime} value */
function toUnixInteger(value) {
    return Math.floor(value.epochMilliseconds / 1000);
}

/** @param {string} seconds */
function fromUnixSeconds(seconds) {
    return fromEpochMilliseconds(parseInt(seconds) * 1000);
}

export class BuilderDateTimePicker extends Component {
    static template = "html_builder.BuilderDateTimePicker";
    static props = {
        ...basicContainerBuilderComponentProps,
        ...textInputBasePassthroughProps,
        type: t.or([t.literal("date"), t.literal("datetime")]).optional("datetime"),
        format: t.string().optional(),
        acceptEmptyDate: t.boolean().optional(true),
    };
    static components = {
        BuilderComponent,
        BuilderTextInputBase,
    };
    props = useProps(this.constructor.props);

    setup() {
        useBuilderComponent();
        this.defaultValue = toUnixInteger(now()).toString();
        const { state, commit, preview } = useInputBuilderComponent({
            id: this.props.id,
            defaultValue: this.props.acceptEmptyDate ? undefined : this.defaultValue,
            formatRawValue: this.formatRawValue.bind(this),
            parseDisplayValue: this.parseDisplayValue.bind(this),
        });
        this.domState = state;
        this.state = proxy({});
        effect(
            ({ value }) => {
                this.state.value = value;
            },
            [state],
        );

        this.commit = (userInputValue) => {
            this.isPreviewing = false;
            const result = commit(userInputValue);
            return result;
        };

        this.preview = (userInputValue) => {
            this.isPreviewing = true;
            preview(userInputValue);
        };

        const minDate = dateTime({ year: 1000 });
        const maxDate = now().add({ years: 200 });
        const getPickerProps = () => {
            const value = this.getCurrentValueDateTime();
            if (this.props.type === "date") {
                return {
                    type: "date",
                    minDate: toDate(minDate),
                    maxDate: toDate(maxDate),
                    value: value && toDate(value),
                    rounding: 0,
                };
            }
            return { type: this.props.type, minDate, maxDate, value, rounding: 0 };
        };

        this.formatDateTime = this.props.type === "date" ? formatDate : formatDateTime;

        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        this.rootRef = elementRef();
        this.dateTimePicker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.rootRef,
            format: this.props.format,
            get pickerProps() {
                return getPickerProps();
            },
            onApply: (value) => {
                this.commit(this.formatDateTime(value));
            },
            onChange: (value) => {
                const dateString = this.formatDateTime(value);
                this.preview(dateString);
                this.state.value = this.parseDisplayValue(dateString);
            },
        });
    }

    /**
     * @returns {Temporal.ZonedDateTime | false} the current value of the datetime picker
     */
    getCurrentValueDateTime() {
        return this.domState.value ? fromUnixSeconds(this.domState.value) : false;
    }

    /**
     * @param {String} rawValue - the raw value in seconds
     * @returns {String} a formatted date string
     */
    formatRawValue(rawValue) {
        return rawValue ? this.formatDateTime(fromUnixSeconds(rawValue)) : "";
    }

    /**
     * @param {String} displayValue - representing a date
     * @returns {String} number of seconds
     */
    parseDisplayValue(displayValue) {
        if (displayValue === "" && this.props.acceptEmptyDate) {
            return undefined;
        }
        try {
            const parsedDateTime = parseDateTime(displayValue);
            if (parsedDateTime) {
                return toUnixInteger(parsedDateTime).toString();
            }
        } catch (e) {
            if (!(e instanceof ConversionError)) {
                throw e;
            }
            if (!this.isPreviewing && displayValue !== "") {
                return this.domState.value;
            }
        }
        return this.defaultValue;
    }

    /**
     * @returns {String} a formatted date string
     */
    get displayValue() {
        return this.state.value !== undefined
            ? this.formatRawValue(this.state.value)
            : undefined;
    }

    get textInputBaseProps() {
        return pick(this.props, ...Object.keys(textInputBasePassthroughProps));
    }

    onFocus() {
        this.dateTimePicker.open();
    }
}
