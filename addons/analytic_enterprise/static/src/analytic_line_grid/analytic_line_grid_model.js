/** @odoo-module native */
import { compareDates, deserializeDate, serializeDate } from "@web/core/l10n/dates";
import { GridModel, GridNavigationInfo } from "@web_grid/views/grid_model";

export class AnalyticLineGridNavigationInfo extends GridNavigationInfo {
    get periodStart() {
        return this._fiscalYearOfAnchor ? this._periodStart : super.periodStart;
    }

    get periodEnd() {
        return this._fiscalYearOfAnchor ? this._periodEnd : super.periodEnd;
    }

    /** @return {boolean} */
    get _fiscalYearOfAnchor() {
        return Boolean(
            this.range.span === "year" &&
            this._periodStart &&
            compareDates(this.anchor, this._periodStart) >= 0 &&
            compareDates(this.anchor, this._periodEnd) <= 0,
        );
    }

    async prepare() {
        if (this.range.span !== "year" || this._fiscalYearOfAnchor) {
            return;
        }
        const { date_from, date_to } = await this.model.orm.call(
            this.model.resModel,
            "grid_compute_year_range",
            [serializeDate(this.anchor)],
        );
        this._periodStart = deserializeDate(date_from);
        this._periodEnd = deserializeDate(date_to);
    }
}

export class AnalyticLineGridModel extends GridModel {
    static NavigationInfo = AnalyticLineGridNavigationInfo;
}
