/** @odoo-module native */
import { compareDates, now } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { RentingMixin } from "@website_sale_renting/js/renting_mixin";

function preparationDuration(hours) {
    return { milliseconds: Math.round(hours * 3600 * 1000) };
}

const oldGetInvalidMessage = RentingMixin._getInvalidMessage;
/**
 * @override
 */
RentingMixin._getInvalidMessage = function (startDate, endDate) {
    const message = oldGetInvalidMessage.apply(this, arguments);
    if (
        message ||
        !startDate ||
        !endDate ||
        !this.rentingAvailabilities ||
        this.preparationTime == null
    ) {
        return message;
    }
    if (
        compareDates(startDate, now().add(preparationDuration(this.preparationTime))) <
        0
    ) {
        return _t("Your rental product cannot be prepared as fast, please rent later.");
    }
    return message;
};

const oldGetExpectedEndDate = RentingMixin._getExpectedEndDate;

/**
 * @override
 */
RentingMixin._getExpectedEndDate = function () {
    let end = oldGetExpectedEndDate.apply(this, arguments);
    if (this._isDurationWithHours() && this.preparationTime) {
        end = end.add(preparationDuration(this.preparationTime));
    }
    return end;
};
