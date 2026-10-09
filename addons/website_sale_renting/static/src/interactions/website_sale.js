/** @odoo-module native */
import {
    deserializeDateTime,
    formatDate,
    formatDateTime,
    serializeDateTime,
} from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { patch } from "@web/core/utils/patch";
import { redirect } from "@web/core/utils/urls";
import { Tooltip } from "@web/libs/bootstrap";
import { TAB_HEADER, TAB_ID } from "@web/public/tab_id";
import { patchDynamicContent } from "@web/public/utils";
import { WebsiteSale } from "@website_sale/interactions/website_sale";
import wSaleUtils from "@website_sale/js/website_sale_utils";
import { RentingMixin } from "@website_sale_renting/js/renting_mixin";

patch(WebsiteSale.prototype, RentingMixin);
patch(WebsiteSale.prototype, {
    setup() {
        super.setup();
        patchDynamicContent(this.dynamicContent, {
            _root: {
                "t-on-renting_constraints_changed":
                    this.onRentingConstraintsChanged.bind(this),
                "t-on-toggle_disable": this.onToggleDisable.bind(this),
                "t-on-daterangepicker_apply": this.onDatePickerApply.bind(this),
            },
            ".js_main_product .o_website_sale_daterange_picker": {
                "t-on-change": this.onChangeVariant.bind(this),
            },
            ".clear-daterange": { "t-on-click": this.onDatePickerClear.bind(this) },
        });
        this.el
            .querySelectorAll('[data-bs-toggle="tooltip"].o_rental_info_message')
            .forEach((el) => {
                const tooltip = Tooltip.getOrCreateInstance(el);
                this.registerCleanup(() => tooltip.dispose());
            });
    },

    async _checkNewDatesOnCart() {
        const response = await this.waitFor(
            rpc("/shop/cart/update_renting", this._getSerializedRentingDates(), {
                headers: { [TAB_HEADER]: TAB_ID },
            }),
        );
        if (!response) {
            return;
        }
        const { start_date, end_date } = response.data;
        this.swapFragments(response);
        const format = this._isDurationWithHours() ? formatDateTime : formatDate;
        document.querySelector("input[name=renting_start_date]").value = format(
            deserializeDateTime(start_date, { tz: this.websiteTz }),
            { tz: this.websiteTz },
        );
        document.querySelector("input[name=renting_end_date]").value = format(
            deserializeDateTime(end_date, { tz: this.websiteTz }),
            { tz: this.websiteTz },
        );
    },

    /**
     * @override
     * @private
     * @returns {void}
     */
    _updateRootProduct() {
        super._updateRootProduct(...arguments);
        Object.assign(this.rootProduct, this._getSerializedRentingDates());
    },

    async onClickAdd(ev) {
        const form = wSaleUtils.getClosestProductForm(ev.currentTarget);
        if (form.querySelector('input[name="is_rental"]')?.value) {
            if (!this._verifyValidRentingPeriod(form)) {
                ev.stopPropagation();
                return Promise.resolve();
            }
        }

        const quantity = await this.waitFor(super.onClickAdd(...arguments));
        const datepickerElements = document.querySelectorAll(
            ".o_website_sale_daterange_picker_input",
        );
        const clearBtnElements = document.querySelectorAll(".clear-daterange");
        const infoMessageElements = document.querySelectorAll(".o_rental_info_message");
        if (quantity > 0) {
            datepickerElements.forEach((elements) => {
                elements.disabled = true;
            });
            clearBtnElements.forEach((elements) => {
                elements.classList.add("d-none");
            });
            infoMessageElements.forEach((elements) => {
                elements.classList.remove("d-none");
            });
        }

        return quantity;
    },

    /**
     * @param {CustomEvent} event
     */
    onRentingConstraintsChanged(event) {
        const info = event.detail;
        if (info.rentingUnavailabilityDays) {
            this.rentingUnavailabilityDays = info.rentingUnavailabilityDays;
        }
        if (info.rentingMinimalTime) {
            this.rentingMinimalTime = info.rentingMinimalTime;
        }
        if (info.websiteTz) {
            this.websiteTz = info.websiteTz;
        }
        if (info.rentingAvailabilities) {
            this.rentingAvailabilities = info.rentingAvailabilities;
        }
    },

    /**
     * @param {CustomEvent} event
     */
    onToggleDisable(event) {
        const { parent, isCombinationAvailable } = event.detail;
        this._toggleDisable(parent, isCombinationAvailable);
    },

    /**
     * @param {Element} parent
     * @private
     */
    _verifyValidRentingPeriod(parent) {
        const rentingDates = this._getRentingDates();
        if (
            !this._verifyValidInput(rentingDates, "start_date") ||
            !this._verifyValidInput(rentingDates, "end_date")
        ) {
            return false;
        }
        const form = wSaleUtils.getClosestProductForm(parent);
        const message = this._getInvalidMessage(
            rentingDates.start_date,
            rentingDates.end_date,
            this._getProductId(form),
        );
        if (message) {
            this.el.querySelector("span[name=renting_warning_message]").innerText =
                message;
        }
        this.el
            .querySelector(".o_renting_warning")
            .classList.toggle("d-block", !!message);
        this._toggleDisable(form, !message);
        return !message;
    },

    /**
     * @param {object} rentingDates
     * @param {string} inputName
     */
    _verifyValidInput(rentingDates, inputName) {
        const input = this.el.querySelector("input[name=renting_" + inputName + "]");
        if (input) {
            input.classList.toggle("is-invalid", !rentingDates[inputName]);
        }
        return rentingDates[inputName];
    },

    /**
     * @param {Event} ev
     * @param {Element} parent
     * @param {Object} combination
     */
    _onChangeCombination(ev, parent, combination) {
        super._onChangeCombination(...arguments);
        if (combination.is_rental) {
            this._verifyValidRentingPeriod(parent);
        }
    },

    /**
     * @param {CustomEvent} event
     */
    onDatePickerApply(event) {
        const { startDate, endDate } = event.detail;
        if (document.querySelector(".oe_cart")) {
            if (startDate && endDate) {
                this._checkNewDatesOnCart();
            }
        } else if (document.querySelector(".o_website_sale_shop_daterange_picker")) {
            this._addDatesToQuery(startDate, endDate);
        }
    },

    _addDatesToQuery(start_date, end_date) {
        const searchParams = new URLSearchParams(window.location.search);
        if (start_date && end_date) {
            searchParams.set("start_date", serializeDateTime(start_date));
            searchParams.set("end_date", serializeDateTime(end_date));
        }
        redirect(`/shop?${searchParams.toString()}`);
    },

    onDatePickerClear() {
        const searchParams = new URLSearchParams(window.location.search);
        searchParams.delete("start_date");
        searchParams.delete("end_date");
        window.location.search = searchParams.toString();
    },
});
