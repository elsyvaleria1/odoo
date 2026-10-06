/** @odoo-module native */
import {
    compareDates,
    ConversionError,
    deserializeDateTime,
    endOf,
    formatDate,
    formatDateTime,
    now,
    parseDate,
    parseDateTime,
    resolveZone,
    serializeDateTime,
    toDateTime,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { sprintf } from "@web/core/utils/format/strings";

export const msecPerUnit = {
    hour: 3600 * 1000,
    day: 3600 * 1000 * 24,
    week: 3600 * 1000 * 24 * 7,
    month: 3600 * 1000 * 24 * 30,
};
export const unitMapping = {
    hour: "hours",
    day: "days",
    week: "weeks",
    month: "months",
};
export const unitMessages = {
    hour: _t("(%s hours)."),
    day: _t("(%s days)."),
    week: _t("(%s weeks)."),
    month: _t("(%s months)."),
};

export const RentingMixin = {
    /**
     * @param {Temporal.ZonedDateTime} startDate
     * @param {Temporal.ZonedDateTime} endDate
     * @param {Number} productId
     * @private
     */
    _getInvalidMessage(startDate, endDate, productId = 0) {
        let message = "";
        if (!this.rentingUnavailabilityDays || !this.rentingMinimalTime) {
            return message;
        }
        if (startDate && endDate) {
            if (this.rentingUnavailabilityDays[startDate.dayOfWeek]) {
                message = _t("You cannot pick up your rental on that day of the week.");
            } else if (this.rentingUnavailabilityDays[endDate.dayOfWeek]) {
                message = _t("You cannot return your rental on that day of the week.");
            } else {
                const rentingDuration =
                    endDate.epochMilliseconds - startDate.epochMilliseconds;
                if (rentingDuration < 0) {
                    message = _t("The return date should be after the pickup date.");
                } else if (
                    compareDates(
                        startDate.startOfDay(),
                        now(this.websiteTz).startOfDay(),
                    ) < 0
                ) {
                    message = _t("The pickup date cannot be in the past.");
                } else if (
                    ["hour", "day", "week", "month"].includes(
                        this.rentingMinimalTime.unit,
                    )
                ) {
                    const { duration, unit } = this.rentingMinimalTime;
                    const minEndDate = startDate.add({
                        [unitMapping[unit]]: duration,
                    });
                    if (compareDates(minEndDate, endDate) > 0) {
                        message = _t(
                            "The rental lasts less than the minimal rental duration %s",
                            sprintf(
                                unitMessages[unit],
                                this.rentingMinimalTime.duration,
                            ),
                        );
                    }
                }
            }
        } else {
            message = _t("Please select a rental period.");
        }
        if (message || !startDate || !endDate || !this.rentingAvailabilities) {
            return message;
        }
        if (!this.rentingAvailabilities[productId]) {
            return message;
        }
        let end;
        for (const interval of this.rentingAvailabilities[productId]) {
            if (compareDates(interval.start, endDate) < 0) {
                end = this._getExpectedEndDate(interval.end);
                if (compareDates(end, startDate) > 0) {
                    if (interval.quantity_available <= 0) {
                        if (!message) {
                            message = _t(
                                "The product is not available for the following time period(s):\n",
                            );
                        }
                        message +=
                            " " +
                            _t("- From %(startPeriod)s to %(endPeriod)s.\n", {
                                startPeriod: this._isDurationWithHours()
                                    ? formatDateTime(interval.start)
                                    : formatDate(interval.start),
                                endPeriod: this._isDurationWithHours()
                                    ? formatDateTime(end)
                                    : formatDate(end),
                            });
                    }
                }
            } else {
                break;
            }
        }
        return message;
    },

    _isDurationWithHours() {
        const unitInput = this.el.querySelector("input[name=rental_duration_unit]");
        return unitInput && unitInput.value === "hour";
    },

    _canSelectHours() {
        const overnightPeriod = this.el.querySelector("input[name=overnight_period]");
        if (overnightPeriod) {
            const isOvernight = overnightPeriod.value === "True";
            return this._isDurationWithHours() && !isOvernight;
        }
        return this._isDurationWithHours();
    },

    _getPickupTime() {
        const defaultStartDate = this.el.querySelector(
            "input[name=default_start_date]",
        ).value;
        const StartDateUTC = parseDateTime(defaultStartDate, { tz: "UTC" });
        const websiteTz = this.el.querySelector("input[name=website_tz]")?.value;
        const dateInWebsiteTzorUTC = websiteTz
            ? StartDateUTC.withTimeZone(resolveZone(websiteTz))
            : StartDateUTC;
        const pickupHour = dateInWebsiteTzorUTC.hour;
        const pickupMinute = dateInWebsiteTzorUTC.minute;

        return [pickupHour, pickupMinute];
    },

    _getReturnTime() {
        const defaultEndDate = this.el.querySelector(
            "input[name=default_end_date]",
        ).value;
        const EndDateUTC = parseDateTime(defaultEndDate, { tz: "UTC" });
        const websiteTz = this.el.querySelector("input[name=website_tz]")?.value;
        const dateInWebsiteTzorUTC = websiteTz
            ? EndDateUTC.withTimeZone(resolveZone(websiteTz))
            : EndDateUTC;
        const returnHour = dateInWebsiteTzorUTC.hour;
        const returnMinute = dateInWebsiteTzorUTC.minute;

        return [returnHour, returnMinute];
    },

    _getExpectedEndDate(endDate) {
        return endDate;
    },

    /**
     * The rental boundary `text` spells, in the website's zone: a day, when
     * the rental is not counted in hours, is the start of that day there.
     *
     * @param {string} text
     * @returns {Temporal.ZonedDateTime | null}
     */
    _parseRentingDate(text) {
        if (this._isDurationWithHours()) {
            return parseDateTime(text, { tz: this.websiteTz });
        }
        const date = parseDate(text, { tz: this.websiteTz });
        return date && toDateTime(date, this.websiteTz);
    },

    /**
     * @private
     */
    _getDateFromInputOrDefault(input, fieldName, inputName) {
        try {
            return this._parseRentingDate(input?.value);
        } catch (e) {
            if (!(e instanceof ConversionError)) {
                throw e;
            }
            const defaultDate = this.el.querySelector(
                'input[name="default_' + inputName + '"]',
            );
            return (
                defaultDate &&
                deserializeDateTime(defaultDate.value, { tz: this.websiteTz })
            );
        }
    },

    /**
     * @private
     * @param {HTMLElement} product
     */
    _getRentingDates(product) {
        const startDate = (product || this.el).querySelector(
            "input[name=renting_start_date]",
        );
        const endDate = (product || this.el).querySelector(
            "input[name=renting_end_date]",
        );
        if (startDate || endDate) {
            let startDateValue = this._getDateFromInputOrDefault(
                startDate,
                "startDate",
                "start_date",
            );
            let endDateValue = this._getDateFromInputOrDefault(
                endDate,
                "endDate",
                "end_date",
            );
            if (!this._canSelectHours() && this._isDurationWithHours()) {
                const [pickupHour, pickupMinute] = this._getPickupTime();
                startDateValue = startDateValue.with({
                    hour: pickupHour,
                    minute: pickupMinute,
                });
                const [returnHour, returnMinute] = this._getReturnTime();
                endDateValue = endDateValue.with({
                    hour: returnHour,
                    minute: returnMinute,
                });
            }
            if (startDateValue && endDateValue && !this._isDurationWithHours()) {
                startDateValue = startDateValue.startOfDay();
                endDateValue = endOf(endDateValue, "day");
            }
            return {
                start_date: startDateValue,
                end_date: endDateValue,
            };
        }
        return {};
    },

    /**
     * @private
     * @param {HTMLElement} product
     */
    _getSerializedRentingDates(product) {
        const { start_date, end_date } = this._getRentingDates(product);
        if (start_date && end_date) {
            return {
                start_date: serializeDateTime(start_date),
                end_date: serializeDateTime(end_date),
            };
        }
    },
};
