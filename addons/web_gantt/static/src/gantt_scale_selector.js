/** @odoo-module native */
import { onWillUpdateProps, proxy, t } from "@odoo/owl";
import { useDateTimePicker } from "@web/components/datetime";
import { useDropdownState } from "@web/components/dropdown";
import { compareDates, formatDate, toDate, toDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { ViewScaleSelector } from "@web/views/view_components";

import { addDuration, useGanttResponsivePopover } from "./gantt_helpers.js";

export class GanttScaleSelector extends ViewScaleSelector {
    static template = "web_gantt.GanttScaleSelector";
    static props = {
        ...ViewScaleSelector.props,
        startDate: t.instanceOf(Temporal.ZonedDateTime),
        stopDate: t.instanceOf(Temporal.ZonedDateTime),
        selectCustomRange: t.function(),
    };

    setup() {
        super.setup();
        this.pickerValues = proxy({
            startDate: this.props.startDate,
            stopDate: this.props.stopDate,
        });

        onWillUpdateProps((nextProps) => {
            this.pickerValues.startDate = nextProps.startDate;
            this.pickerValues.stopDate = nextProps.stopDate;
        });

        const getPickerProps = (key) => ({
            type: "date",
            value: toDate(this.pickerValues[key]),
        });
        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        this.startPickerRef = elementRef();
        this.startPicker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.startPickerRef,
            onApply: (value) => {
                const date = toDateTime(value);
                this.pickerValues.startDate = date;
                const tenYearsAfter = addDuration(date, { years: 10, days: -1 });
                if (compareDates(this.pickerValues.stopDate, date) < 0) {
                    this.pickerValues.stopDate = date;
                } else if (
                    compareDates(tenYearsAfter, this.pickerValues.stopDate) < 0
                ) {
                    this.pickerValues.stopDate = tenYearsAfter;
                }
            },
            get pickerProps() {
                return getPickerProps("startDate");
            },
            createPopover: (...args) =>
                useGanttResponsivePopover(_t("Gantt start date"), ...args),
            ensureVisibility: () => false,
        });
        this.stopPickerRef = elementRef();
        this.stopPicker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.stopPickerRef,
            onApply: (value) => {
                const date = toDateTime(value);
                this.pickerValues.stopDate = date;
                if (compareDates(date, this.pickerValues.startDate) < 0) {
                    this.pickerValues.startDate = date;
                } else if (
                    compareDates(
                        addDuration(this.pickerValues.startDate, {
                            years: 10,
                            days: -1,
                        }),
                        date,
                    ) < 0
                ) {
                    this.pickerValues.startDate = addDuration(date, {
                        years: -10,
                        days: 1,
                    });
                }
            },
            get pickerProps() {
                return getPickerProps("stopDate");
            },
            createPopover: (...args) =>
                useGanttResponsivePopover(_t("Gantt stop date"), ...args),
            ensureVisibility: () => false,
        });

        this.dropdownState = useDropdownState({
            onClose: () => {
                this.pickerValues.startDate = this.props.startDate;
                this.pickerValues.stopDate = this.props.stopDate;
            },
        });
    }

    getFormattedDate(date) {
        return formatDate(date);
    }

    onApply() {
        const { startDate, stopDate } = this.pickerValues;
        this.props.selectCustomRange(startDate, stopDate);
        this.dropdownState.close();
    }
}
