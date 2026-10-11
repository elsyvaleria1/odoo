// @ts-check
/** @odoo-module native */

import { proxy, t } from "@odoo/owl";
import { formatRangeDuration } from "@web/components/datetime/datetime_picker";
import { useDateTimePicker } from "@web/components/datetime/datetime_picker_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { formatFieldDate, formatFieldDateTime } from "@web/core/formatters";
import {
    areDatesEqual,
    compareDates,
    deserializeDate,
    deserializeDateTime,
    endOf,
    hasSame,
    isDateOrDateTimeValue,
    now,
    toDateTime,
    today,
} from "@web/core/l10n/dates";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { _t } from "@web/core/translation";
import { ensureArray } from "@web/core/utils/collections/arrays";
import { pick } from "@web/core/utils/collections/objects";
import { elementRef } from "@web/core/utils/element_ref";
import { exprToBoolean } from "@web/core/utils/format/strings";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { registerField } from "@web/fields/_registry";
import { FieldComponent } from "@web/fields/field_component";
import { useFieldDirtySignal } from "@web/fields/field_dirty_signal";
import {
    datePrecisionOptions,
    placeholderFieldOption,
} from "@web/fields/field_options";
import { FIELD_WIDTHS } from "@web/fields/field_widths";
import { useFieldFlush } from "@web/fields/hooks/debounced_field_commit";
import { standardFieldProps } from "@web/fields/standard_field_props";

const log = makeLogger("web.fields.datetime");

function getFormattedPlaceholder(value, type, options) {
    if (isDateOrDateTimeValue(value)) {
        return type === "date"
            ? formatFieldDate(value, options)
            : formatFieldDateTime(value, options);
    }
    return value || "";
}

/**
 * @typedef {import("@web/fields/standard_field_props").StandardFieldProps & {
 * endDateField?: string;
 * maxDate?: string;
 * minDate?: string;
 * placeholder?: string;
 * required?: boolean;
 * rounding?: number;
 * startDateField?: string;
 * warnFuture?: boolean;
 * showSeconds?: boolean;
 * showTime?: boolean;
 * numeric?: boolean;
 * minPrecision?: string;
 * maxPrecision?: string;
 * alwaysRange?: boolean;
 * showDuration?: boolean;
 * }} DateTimeFieldProps
 * @typedef {import("@web/components/datetime/datetime_picker").DateTimePickerProps} DateTimePickerProps
 * @typedef {import("@web/core/l10n/dates").NullableDateRange} NullableDateRange
 */

/** @extends {FieldComponent<DateTimeFieldProps>} */
export class DateTimeField extends FieldComponent {
    static props = {
        ...standardFieldProps,
        endDateField: t.string().optional(),
        maxDate: t.string().optional(),
        minDate: t.string().optional(),
        alwaysRange: t.boolean().optional(),
        showDuration: t.boolean().optional(false),
        placeholder: t.string().optional(),
        required: t.boolean().optional(),
        rounding: t.number().optional(),
        startDateField: t.string().optional(),
        numeric: t.boolean().optional(false),
        warnFuture: t.boolean().optional(),
        showSeconds: t.boolean().optional(false),
        showTime: t.boolean().optional(true),
        minPrecision: t
            .customValidator(t.string(), (props) =>
                ["days", "months", "years", "decades"].includes(props),
            )
            .optional(),
        maxPrecision: t
            .customValidator(t.string(), (props) =>
                ["days", "months", "years", "decades"].includes(props),
            )
            .optional(),
    };

    static template = "web.DateTimeField";

    get endDateField() {
        return this.relatedField ? this.props.endDateField || this.props.name : null;
    }

    get fieldDefinition() {
        return this.field.definition;
    }

    get relatedField() {
        return this.props.startDateField || this.props.endDateField;
    }

    get startDateField() {
        return this.props.startDateField || this.props.name;
    }

    get values() {
        return ensureArray(this.state.value);
    }

    setup() {
        this.ui = useService("ui");
        this._pendingFocusField = "";
        /** @type {{ key: string, promise: Promise<void> } | null} */
        this._urgentUpdate = null;

        const getPickerProps = () => this.getPickerProps();
        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        this.rootRef = elementRef();
        const dateTimePicker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.rootRef,
            showSeconds: this.props.showSeconds,
            get pickerProps() {
                return getPickerProps();
            },
            onChange: () => {
                this.state.range = this.isRange(this.state.value);
            },
            onClose: () => {
                this.picker.activeInput = "";
            },
            onApply: () => this.applyPickedValues(),
        });
        this.state = proxy(dateTimePicker.state);
        this.picker = proxy({ activeInput: "" });
        this.openPicker = dateTimePicker.open;

        useFieldFlush(this.props.record.model.bus, (ev, urgent) => {
            const committed = dateTimePicker.commitInputs();
            if (!urgent) {
                ev.detail?.proms?.push(committed);
                return;
            }
            committed.catch(() => {});
            ev.detail?.proms?.push(this.applyPickedValues());
        });

        this.startDate = this.startDateRef;
        this.endDate = this.endDateRef;
        this.setupFocusRestore();

        this.setFieldDirty = useFieldDirtySignal();
        useLayoutEffect(() => this.triggerIsDirty());

        this.futureWarningMsg = _t("This date is in the future");
    }

    setupFocusRestore() {
        useLayoutEffect(
            () => {
                [this.startDate, this.endDate].forEach((ref, index) => {
                    const fieldAttr = ref.el?.getAttribute("data-field");
                    if (fieldAttr === this.picker.activeInput) {
                        ref.el.focus();
                        this.openPicker(index);
                    } else if (
                        this._pendingFocusField &&
                        ref.el?.tagName === "BUTTON" &&
                        fieldAttr === this._pendingFocusField
                    ) {
                        this._suppressNextFocus = true;
                        ref.el.focus();
                        this._pendingFocusField = "";
                    }
                });
            },
            () => [
                this.startDate.el?.tagName,
                this.endDate.el?.tagName,
                this.picker.activeInput,
            ],
        );
    }

    /** @returns {Promise<void>} */
    async applyPickedValues() {
        const toUpdate = {};
        if (Array.isArray(this.state.value)) {
            [toUpdate[this.startDateField], toUpdate[this.endDateField]] =
                this.state.value;
        } else {
            toUpdate[this.props.name] = this.state.value;
        }

        for (const fieldName of Object.keys(toUpdate)) {
            if (areDatesEqual(toUpdate[fieldName], this.props.record.data[fieldName])) {
                delete toUpdate[fieldName];
            }
        }

        if (!Object.keys(toUpdate).length) {
            return;
        }
        const urgent = this.props.record.model.urgentSave.isActive;
        const key = JSON.stringify(toUpdate);
        const reissued = urgent && this._urgentUpdate?.key === key;
        log.logic("apply picked values", () => ({
            field: this.props.name,
            urgent,
            reissued,
            values: key,
        }));
        if (reissued) {
            return /** @type {{ promise: Promise<void> }} */ (this._urgentUpdate)
                .promise;
        }
        this._pendingFocusField = this.picker.activeInput;
        const promise = this.props.record.update(toUpdate);
        if (urgent) {
            const urgentUpdate = { key, promise };
            this._urgentUpdate = urgentUpdate;
            const forget = () => {
                if (this._urgentUpdate === urgentUpdate) {
                    this._urgentUpdate = null;
                }
            };
            promise.then(forget, forget);
        }
        await promise;
    }

    onToggleRange() {
        this.state.range = !this.state.range;

        if (this.state.range) {
            const [start, end] = this.values;
            /** @type {import("@web/core/l10n/dates").NullableDateValue[]} */
            let values;
            if (this.fieldDefinition.type === "date") {
                const anchor = start || end || today();
                values = [anchor, anchor];
            } else {
                const anchor = end || now();
                values = start
                    ? [start, start.add({ hours: 1 })]
                    : [anchor.subtract({ hours: 1 }), anchor];
            }

            this.state.focusedDateIndex = 0;
            this.state.value = values;
        } else {
            const mainFieldIndex = this.props.name === this.startDateField ? 0 : 1;

            this.state.focusedDateIndex = mainFieldIndex;
            this.state.value[mainFieldIndex ? 0 : 1] = false;
        }
    }

    /** @returns {DateTimePickerProps} */
    getPickerProps() {
        const value = this.getRecordValue();
        /** @type {DateTimePickerProps} */
        const pickerProps = {
            value,
            type: /** @type {any} */ (this.fieldDefinition.type),
            range: this.isRange(value),
            showRangeToggler: Boolean(
                this.relatedField && !this.props.required && !this.props.alwaysRange,
            ),
            onToggleRange: () => this.onToggleRange(),
        };
        if (this.relatedField) {
            pickerProps.boundLabels = [
                this.getFieldString(this.startDateField),
                this.getFieldString(this.endDateField),
            ];
            pickerProps.monthCount = this.ui.isSmall ? 1 : 2;
            pickerProps.showPresets = true;
        }
        if (this.props.maxDate) {
            pickerProps.maxDate = this.parseLimitDate(this.props.maxDate, "max");
        }
        if (this.props.minDate) {
            pickerProps.minDate = this.parseLimitDate(this.props.minDate, "min");
        }
        if (!isNaN(/** @type {any} */ (this.props.rounding))) {
            pickerProps.rounding = this.props.rounding;
        } else if (this.props.showSeconds) {
            pickerProps.rounding = 0;
        }
        if (this.props.maxPrecision) {
            pickerProps.maxPrecision = /** @type {any} */ (this.props.maxPrecision);
        }
        if (this.props.minPrecision) {
            pickerProps.minPrecision = /** @type {any} */ (this.props.minPrecision);
        }
        return pickerProps;
    }

    /** @param {FocusEvent} ev */
    onDateButtonFocus(ev) {
        if (this._suppressNextFocus) {
            this._suppressNextFocus = false;
            return;
        }
        this.picker.activeInput = /** @type {HTMLElement} */ (
            ev.currentTarget
        ).getAttribute("data-field");
    }

    /** @param {MouseEvent} ev */
    onDateButtonClick(ev) {
        this.picker.activeInput = /** @type {HTMLElement} */ (
            ev.currentTarget
        ).getAttribute("data-field");
    }

    /**
     * @param {number} valueIndex
     * @param {boolean} [numeric=this.props.numeric]
     */
    getFormattedValue(valueIndex, numeric = this.props.numeric) {
        const values = this.values;
        const value = values[valueIndex];
        if (!value) {
            return "";
        }
        const { showSeconds, showTime } = this.props;
        if (this.fieldDefinition.type === "date") {
            return formatFieldDate(value, { numeric });
        } else {
            const showDate =
                !showTime ||
                valueIndex !== 1 ||
                !values[0] ||
                !hasSame(values[0], value, "day");
            return formatFieldDateTime(value, {
                numeric,
                showSeconds,
                showTime,
                showDate,
            });
        }
    }

    /** @param {string} fieldName */
    getFieldString(fieldName) {
        return this.props.record.fields[fieldName]?.string || fieldName;
    }

    /**
     * An empty bound of a range is named after its field, so that the user
     * sees which end is which before picking anything
     *
     * @param {string} fieldName
     */
    getPlaceholder(fieldName) {
        if (this.props.placeholder || !this.relatedField) {
            return this.props.placeholder;
        }
        return this.getFieldString(fieldName);
    }

    /** @returns {{ short: string, long: string } | null} */
    get duration() {
        const [start, end] = this.values;
        if (
            !this.props.showDuration ||
            !start ||
            !end ||
            compareDates(end, start) < 0
        ) {
            return null;
        }
        const type = this.fieldDefinition.type;
        return {
            short: formatRangeDuration(start, end, type, false),
            long: formatRangeDuration(start, end, type),
        };
    }

    /** @returns {DateTimePickerProps["value"]} */
    getRecordValue() {
        if (this.relatedField) {
            return [
                this.props.record.data[this.startDateField],
                this.props.record.data[this.endDateField],
            ];
        } else {
            return this.field.value;
        }
    }

    /** @param {number} index */
    isDateInTheFuture(index) {
        const value = this.values[index];
        if (!value) {
            return false;
        }
        const reference = this.fieldDefinition.type === "date" ? today() : now();
        return compareDates(value, reference) > 0;
    }

    /** @param {string} fieldName */
    isEmpty(fieldName) {
        return fieldName === this.startDateField ? !this.values[0] : !this.values[1];
    }

    /**
     * @param {DateTimePickerProps["value"]} value
     * @returns {boolean}
     */
    isRange(value) {
        if (!this.relatedField) {
            return false;
        }
        return (
            this.props.alwaysRange ||
            this.props.required ||
            ensureArray(value).filter(Boolean).length === 2
        );
    }

    /**
     * @param {string} value
     * @param {"min" | "max"} [boundary]
     */
    parseLimitDate(value, boundary) {
        if (value === "today") {
            return value;
        }
        if (this.fieldDefinition.type === "date") {
            return deserializeDate(value);
        }
        if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
            const dayStart = toDateTime(deserializeDate(value));
            return boundary === "max" ? endOf(dayStart, "day") : dayStart;
        }
        return deserializeDateTime(value);
    }

    /** @return {boolean} */
    shouldShowSeparator() {
        const bothEnds =
            !this.isEmpty(this.startDateField) && !this.isEmpty(this.endDateField);
        const eitherEnd =
            !this.isEmpty(this.startDateField) || !this.isEmpty(this.endDateField);
        if (this.props.alwaysRange) {
            return this.props.readonly ? eitherEnd : true;
        }
        return Boolean(this.state.range && (this.props.required || bothEnds));
    }

    /** @param {boolean} [isDirty] */
    triggerIsDirty(isDirty) {
        this.setFieldDirty(
            isDirty ?? !areDatesEqual(this.getRecordValue(), this.state.value),
        );
    }

    onInput() {
        this.triggerIsDirty(true);
    }
}

const START_DATE_FIELD_OPTION = "start_date_field";
const END_DATE_FIELD_OPTION = "end_date_field";

/**
 * @param {Record<string, any>} options
 * @returns {number}
 */
function dateListViewWidth(options) {
    return exprToBoolean(options.numeric ?? false)
        ? FIELD_WIDTHS.numeric_date
        : FIELD_WIDTHS.date;
}

/**
 * @param {Record<string, any>} options
 * @returns {number}
 */
function dateTimeListViewWidth(options) {
    if (!exprToBoolean(options.show_time ?? true)) {
        return dateListViewWidth(options);
    }
    if (exprToBoolean(options.numeric ?? false)) {
        return FIELD_WIDTHS.numeric_datetime;
    }
    return exprToBoolean(options.show_seconds ?? false)
        ? FIELD_WIDTHS.datetime_seconds
        : FIELD_WIDTHS.datetime;
}

/**
 * @param {Record<string, any>} staticInfo
 * @param {Record<string, any>} dynamicInfo
 * @param {{ numeric: boolean, showSeconds?: boolean, showTime?: boolean }} format
 * @returns {Record<string, any>}
 */
function extractDateProps({ options, placeholder, type }, dynamicInfo, format) {
    return {
        endDateField: options[END_DATE_FIELD_OPTION],
        maxDate: options.max_date,
        minDate: options.min_date,
        alwaysRange: exprToBoolean(options.always_range),
        showDuration: exprToBoolean(options.show_duration ?? false),
        placeholder: getFormattedPlaceholder(placeholder, type, format),
        required: dynamicInfo.required,
        rounding: options.rounding && Number.parseInt(options.rounding, 10),
        startDateField: options[START_DATE_FIELD_OPTION],
        warnFuture: exprToBoolean(options.warn_future),
        minPrecision: options.min_precision,
        maxPrecision: options.max_precision,
        ...format,
    };
}

/** @satisfies {import("registries").FieldsRegistryItemShape} */
export const dateField = {
    component: DateTimeField,
    displayName: _t("Date"),
    supportedOptions: [
        {
            label: _t("Earliest accepted date"),
            name: "min_date",
            type: "string",
            help: _t('ISO-formatted date (e.g. "2018-12-31") or "%s".', "today"),
        },
        {
            label: _t("Latest accepted date"),
            name: "max_date",
            type: "string",
            help: _t('ISO-formatted date (e.g. "2018-12-31") or "%s".', "today"),
        },
        {
            label: _t("Warning for future dates"),
            name: "warn_future",
            type: "boolean",
            help: _t("Displays a warning icon if the input dates are in the future."),
        },
        ...datePrecisionOptions(),
        {
            label: _t("Date Format"),
            name: "numeric",
            type: "selection",
            help: _t(
                "Displays the date either in 31/01/%(year)s or in Jan 31, %(year)s",
                {
                    year: today().year,
                },
            ),
            placeholder: _t("Jan 31, %s", today().year),
            choices: [
                { label: _t("Jan 31, %s", today().year), value: false },
                { label: _t("31/01/%s", today().year), value: true },
            ],
        },
        placeholderFieldOption(["date", "datetime", "char"]),
    ],
    supportedTypes: ["date", "datetime"],
    extractProps: (staticInfo, dynamicInfo) =>
        extractDateProps(staticInfo, dynamicInfo, {
            numeric: exprToBoolean(staticInfo.options.numeric ?? false),
            showTime: false,
        }),
    listViewWidth: ({ options }) => dateListViewWidth(options),
    fieldDependencies: ({ type, attrs, options }) => {
        const modifiers = pick(attrs, "invisible", "readonly", "required");
        const dependency = (name) => ({ name, type, readonly: false, ...modifiers });
        if (options[START_DATE_FIELD_OPTION]) {
            if (options[END_DATE_FIELD_OPTION]) {
                console.warn(
                    `A field cannot have both ${START_DATE_FIELD_OPTION} and ${END_DATE_FIELD_OPTION} options at the same time`,
                );
            }
            return [dependency(options[START_DATE_FIELD_OPTION])];
        }
        if (options[END_DATE_FIELD_OPTION]) {
            return [dependency(options[END_DATE_FIELD_OPTION])];
        }
        return [];
    },
};

/** @satisfies {import("registries").FieldsRegistryItemShape} */
export const dateTimeField = {
    ...dateField,
    displayName: _t("Date & Time"),
    supportedOptions: [
        ...dateField.supportedOptions.filter((o) => o.name !== "placeholder_field"),
        {
            label: _t("Time interval"),
            name: "rounding",
            type: "number",
            default: 5,
            help: _t(
                `Control the number of minutes in the time selection. E.g. set it to 15 to work in quarters.`,
            ),
        },
        {
            label: _t("Show time"),
            name: "show_time",
            type: "boolean",
            default: true,
            help: _t("Displays or hides the time in the datetime value."),
        },
        {
            label: _t("Show seconds"),
            name: "show_seconds",
            type: "boolean",
            default: false,
            help: _t(
                `Displays or hides the seconds in the datetime value. Affect only the readable datetime format.`,
            ),
        },
        placeholderFieldOption(["datetime", "char"]),
    ],
    extractProps: (staticInfo, dynamicInfo) => {
        const { options } = staticInfo;
        return extractDateProps(staticInfo, dynamicInfo, {
            numeric: exprToBoolean(options.numeric ?? false),
            showSeconds: exprToBoolean(options.show_seconds ?? false),
            showTime: exprToBoolean(options.show_time ?? true),
        });
    },
    supportedTypes: ["datetime"],
    listViewWidth: ({ options }) => dateTimeListViewWidth(options),
};

/** @satisfies {import("registries").FieldsRegistryItemShape} */
export const dateRangeField = {
    ...dateTimeField,
    displayName: _t("Date Range"),
    supportedOptions: [
        ...dateTimeField.supportedOptions.filter((o) => o.name !== "placeholder_field"),
        {
            label: _t("Start date field"),
            name: START_DATE_FIELD_OPTION,
            type: "field",
            availableTypes: ["date", "datetime"],
        },
        {
            label: _t("End date field"),
            name: END_DATE_FIELD_OPTION,
            type: "field",
            availableTypes: ["date", "datetime"],
        },
        {
            label: _t("Always range"),
            name: "always_range",
            type: "boolean",
            default: false,
            help: _t(
                `Set to true the full range input has to be display by default, even if empty.`,
            ),
        },
        {
            label: _t("Show duration"),
            name: "show_duration",
            type: "boolean",
            default: false,
            help: _t("Displays how long the range lasts next to its end."),
        },
        placeholderFieldOption(["date", "datetime", "char"]),
    ],
    supportedTypes: ["date", "datetime"],
    listViewWidth: ({ type, options }) => {
        const width =
            type === "datetime"
                ? dateTimeListViewWidth(options)
                : dateListViewWidth(options);
        return width ? 2 * width + 30 : undefined;
    },
    isValid: (record, fieldname, fieldInfo) => {
        if (fieldInfo.widget === "daterange") {
            const thisEndIsEmpty = !record.data[fieldname];
            for (const option of [END_DATE_FIELD_OPTION, START_DATE_FIELD_OPTION]) {
                const otherEnd = fieldInfo.options[option];
                if (!otherEnd) {
                    continue;
                }
                if (
                    !record.data[otherEnd] !== thisEndIsEmpty &&
                    evaluateBooleanExpr(
                        record.activeFields[otherEnd]?.required,
                        record.evalContextWithVirtualIds,
                    )
                ) {
                    return false;
                }
            }
        }
        return !record.isFieldInvalid(fieldname);
    },
};

registerField("date", dateField);
registerField("daterange", dateRangeField);
registerField("datetime", dateTimeField);
