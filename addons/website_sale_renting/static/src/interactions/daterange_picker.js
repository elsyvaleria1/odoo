/** @odoo-module native */
import {
    areDatesEqual,
    compareDates,
    deserializeDateTime,
    maxDate,
    minDate,
    now,
    serializeDateTime,
    toDate,
    toDateTime,
} from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import wSaleUtils from "@website_sale/js/website_sale_utils";
import { RentingMixin, unitMapping } from "@website_sale_renting/js/renting_mixin";

export class DaterangePicker extends Interaction {
    static selector = ".o_website_sale_daterange_picker";
    rentingAvailabilities = {};

    setup() {
        this.isShopDatePicker = this.el.classList.contains(
            "o_website_sale_shop_daterange_picker",
        );
        this.disableDateTimePickers = [];
    }

    async willStart() {
        await this._loadRentingConstraints();
    }

    start() {
        this.startDate = this._getDefaultRentingDate("start_date");
        this.endDate = this._getDefaultRentingDate("end_date");
        this.el
            .querySelectorAll(".o_daterange_picker")
            .forEach((el) => this._initSaleRentingDateRangePicker(el));
        this._verifyValidPeriod();
    }

    destroy() {
        for (const disableDateTimePicker of this.disableDateTimePickers) {
            disableDateTimePicker();
        }
    }

    /**
     * @returns {*}
     * @private
     */
    _hasDefaultDates() {
        return (
            (this._getSearchDefaultRentingDate("start_date") &&
                this._getSearchDefaultRentingDate("end_date")) ||
            (this.el.querySelector('input[name="default_start_date"]') &&
                this.el.querySelector('input[name="default_end_date"]'))
        );
    }

    /**
     * @private
     */
    async _loadRentingConstraints() {
        const constraints = await this.waitFor(rpc("/rental/product/constraints"));
        this.rentingUnavailabilityDays = constraints.renting_unavailabity_days;
        this.rentingMinimalTime = constraints.renting_minimal_time;
        this.websiteTz = constraints.website_tz;
        this._triggerRentingConstraintsChanged({
            rentingUnavailabilityDays: this.rentingUnavailabilityDays,
            rentingMinimalTime: this.rentingMinimalTime,
            websiteTz: this.websiteTz,
        });
    }

    /**
     * @param {HTMLElement} el
     * @private
     */
    _initSaleRentingDateRangePicker(el) {
        const hasDefaultDates = Boolean(this._hasDefaultDates());
        el.dataset.hasDefaultDates = hasDefaultDates;
        const type = this._canSelectHours() ? "datetime" : "date";
        // A date picker holds days: the rental's datetimes are shown as the
        // days they fall on in the website's zone, and read back as the start
        // of those days there.
        const toPicker = (value) => (type === "date" ? toDate(value) : value);
        const fromPicker = (value) => value && toDateTime(value, this.websiteTz);
        const value =
            this.isShopDatePicker && !hasDefaultDates
                ? ["", ""]
                : [toPicker(this.startDate), toPicker(this.endDate)];
        const datetimeWebsiteTz = now(this.websiteTz);
        this.disableDateTimePickers.push(
            this.services["datetime_picker"]
                .create({
                    target: el,
                    pickerProps: {
                        value,
                        range: true,
                        type,
                        minDate: toPicker(minDate(datetimeWebsiteTz, this.startDate)),
                        maxDate: toPicker(
                            maxDate(datetimeWebsiteTz.add({ years: 3 }), this.endDate),
                        ),
                        isDateValid: this._isValidDate.bind(this),
                        dayCellClass: (date) =>
                            this._isCustomDate(date, this.startDate).join(" "),
                        tz: this.websiteTz,
                    },
                    onApply: (range) => {
                        const [startDate, endDate] = range.map(fromPicker);
                        if (!this._canSelectHours() && this._isDurationWithHours()) {
                            const [pickupHour, pickupMinute] = this._getPickupTime();
                            const startDateWithTime = startDate.with({
                                hour: pickupHour,
                                minute: pickupMinute,
                            });
                            const [returnHour, returnMinute] = this._getReturnTime();
                            const endDateWithTime = endDate.with({
                                hour: returnHour,
                                minute: returnMinute,
                            });
                            if (
                                areDatesEqual(
                                    [this.startDate, this.endDate],
                                    [startDateWithTime, endDateWithTime],
                                )
                            ) {
                                return;
                            }
                            this.startDate = startDateWithTime;
                            this.endDate = endDateWithTime;
                        } else {
                            if (
                                areDatesEqual(
                                    [this.startDate, this.endDate],
                                    [startDate, endDate],
                                )
                            ) {
                                return;
                            }
                            this.startDate = startDate;
                            this.endDate = endDate;
                        }
                        this._verifyValidPeriod();
                        this.el
                            .querySelector("input[name=renting_start_date]")
                            .dispatchEvent(new Event("change", { bubbles: true }));
                        this.el.dispatchEvent(
                            new CustomEvent("daterangepicker_apply", {
                                detail: {
                                    startDate: this.startDate,
                                    endDate: this.endDate,
                                },
                                bubbles: true,
                            }),
                        );
                    },
                    getInputs: () => [
                        el.querySelector("input[name=renting_start_date]"),
                        el.querySelector("input[name=renting_end_date]"),
                    ],
                })
                .enable(),
        );
    }

    async _fetchProductAvailabilities(productId, minDate, maxDate) {
        const result = await this.waitFor(
            rpc("/rental/product/availabilities", {
                product_id: productId,
                min_date: minDate,
                max_date: maxDate,
            }),
        );
        this.rentingAvailabilities[productId] = [];
        if (result.renting_availabilities?.length) {
            this.rentingAvailabilities[productId] = result.renting_availabilities.map(
                (rentingAvailabilities) => {
                    const { start, end, ...rest } = rentingAvailabilities;
                    return {
                        start: deserializeDateTime(start),
                        end: deserializeDateTime(end),
                        ...rest,
                    };
                },
            );
        }
        this.preparationTime = result.preparation_time;
    }

    /**
     * @param {String} inputName
     * @private
     */
    _getDefaultRentingDate(inputName) {
        const defaultDate = this._getSearchDefaultRentingDate(inputName);
        if (defaultDate) {
            return deserializeDateTime(defaultDate);
        }
        const defaultDateEl = this.el.querySelector(
            `input[name="default_${inputName}"]`,
        );
        if (defaultDateEl) {
            return deserializeDateTime(defaultDateEl.value, { tz: this.websiteTz });
        }
        if (this.startDate) {
            const { duration, unit } = this.rentingMinimalTime;
            const minEndDate = this.startDate.add({ [unitMapping[unit]]: duration });
            const defaultEndDate = this.startDate.add({ days: 1 });
            const endDate = maxDate(minEndDate, defaultEndDate);
            return this._getFirstAvailableDate(endDate);
        }
        const date = now().add({ days: 1, hours: 1 }).with({ minute: 0, second: 0 });
        return this._getFirstAvailableDate(date);
    }

    /**
     * @param {String} inputName
     * @private
     */
    _getSearchDefaultRentingDate(inputName) {
        return new URLSearchParams(window.location.search).get(inputName);
    }

    /**
     * @param {Temporal.PlainDate | Temporal.ZonedDateTime} date
     * @private
     */
    _isValidDate(date) {
        return !this.rentingUnavailabilityDays[date.dayOfWeek];
    }

    /**
     * @param {Temporal.PlainDate | Temporal.ZonedDateTime} date a picker day
     * @param {Temporal.ZonedDateTime} startDate
     * @private
     */
    _isCustomDate(date, startDate) {
        const result = [];
        const productId = this._getProductId();
        if (!productId || !this.rentingAvailabilities[productId]) {
            return result;
        }
        const dateStart = toDateTime(toDate(date), this.websiteTz).with({
            hour: startDate.hour,
            minute: startDate.minute,
        });
        for (const interval of this.rentingAvailabilities[productId]) {
            if (compareDates(interval.start, dateStart) > 0) {
                return result;
            }
            if (
                compareDates(interval.end, dateStart) > 0 &&
                interval.quantity_available <= 0
            ) {
                result.push("o_daterangepicker_danger");
                return result;
            }
        }
        return result;
    }

    /**
     * @private
     */
    _verifyValidPeriod() {
        const message = this._getInvalidMessage(
            this.startDate,
            this.endDate,
            this._getProductId(),
        );
        if (message) {
            this.el.parentElement.querySelector(
                "span[name=renting_warning_message]",
            ).innerText = message;
            this.el.parentElement
                .querySelector(".o_renting_warning")
                .classList.add("d-block");
        } else {
            this.el.parentElement
                .querySelector(".o_renting_warning")
                .classList.remove("d-block");
        }
        const form = wSaleUtils.getClosestProductForm(this.el);
        if (form) {
            document.querySelector(".oe_website_sale")?.dispatchEvent(
                new CustomEvent("toggle_disable", {
                    detail: { parent: form, isCombinationAvailable: !message },
                }),
            );
        }
        this.el.dispatchEvent(
            new CustomEvent("toggle_search_btn", { bubbles: true, detail: message }),
        );
        return !message;
    }

    _getProductId() {
        if (!this.productId) {
            const productSelector = [
                'input[type="hidden"][name="product_id"]',
                'input[type="radio"][name="product_id"]:checked',
            ];
            const form = wSaleUtils.getClosestProductForm(this.el);
            const productInput = form && form.querySelector(productSelector.join(", "));
            this.productId = productInput && parseInt(productInput.value);
        }
        return this.productId;
    }

    /**
     * @private
     */
    _getFirstAvailableDate(date) {
        let counter = 0;
        while (!this._isValidDate(date) && counter < 1000) {
            date = date.add({ days: 1 });
            counter++;
        }
        return date;
    }

    _triggerRentingConstraintsChanged(vals) {
        document
            .querySelector(".oe_website_sale")
            ?.dispatchEvent(
                new CustomEvent("renting_constraints_changed", { detail: vals || {} }),
            );
    }

    /**
     * @private
     */
    async _updateRentingProductAvailabilities() {
        const productId = this._getProductId();
        if (!productId || this.rentingAvailabilities[productId]) {
            return;
        }
        await this.waitFor(
            this._fetchProductAvailabilities(
                productId,
                serializeDateTime(now()),
                serializeDateTime(now().add({ years: 3 })),
            ),
        );
        this._triggerRentingConstraintsChanged({
            rentingAvailabilities: this.rentingAvailabilities,
            preparationTime: this.preparationTime,
        });
        this._verifyValidPeriod();
    }
}

Object.assign(DaterangePicker.prototype, RentingMixin);

registry
    .category("public.interactions")
    .add("website_sale_renting.daterange_picker", DaterangePicker);
