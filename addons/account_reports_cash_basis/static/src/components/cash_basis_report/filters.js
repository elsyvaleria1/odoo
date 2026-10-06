/** @odoo-module native */
import { AccountReportFilters } from "@report_formula/components/account_report/filters/filters";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(AccountReportFilters.prototype, {
    get filterExtraOptionsData() {
        return {
            ...super.filterExtraOptionsData,
            report_cash_basis: {
                name: _t("Cash Basis Method"),
                group: "account_user",
                show: this.controller.filters.show_cash_basis,
            },
        };
    },

    get selectedExtraOptions() {
        let selectedExtraOptionsName = super.selectedExtraOptions;
        if (this.controller.filters.show_cash_basis) {
            const cashBasisFilterName = this.controller.cachedFilterOptions
                .report_cash_basis
                ? _t("Cash Basis")
                : _t("Accrual Basis");

            selectedExtraOptionsName = selectedExtraOptionsName
                ? `${selectedExtraOptionsName}, ${cashBasisFilterName}`
                : cashBasisFilterName;
        }
        return selectedExtraOptionsName;
    },
});
