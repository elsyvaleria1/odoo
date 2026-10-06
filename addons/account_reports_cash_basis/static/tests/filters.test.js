// Importing the module applies its patch() on AccountReportFilters.prototype.
import "@account_reports_cash_basis/components/cash_basis_report/filters";

import { expect, test } from "@odoo/hoot";
import { AccountReportFilters } from "@report_formula/components/account_report/filters/filters";

/**
 * The cash-basis filters module only patches two getters on
 * AccountReportFilters.prototype; mounting the whole component (Dropdown,
 * services, ...) would test far more than this module owns. Call the
 * patched getters directly against a minimal fake `this`, the same way the
 * component itself would see them via `this.controller`.
 */
function fakeFilters({ showCashBasis, reportCashBasis, group = true } = {}) {
    return {
        controller: {
            filters: { show_cash_basis: showCashBasis },
            cachedFilterOptions: { report_cash_basis: reportCashBasis },
            cachedUserGroups: { account_user: group },
        },
    };
}

function getFilterExtraOptionsData(fakeThis) {
    return Object.getOwnPropertyDescriptor(
        AccountReportFilters.prototype,
        "filterExtraOptionsData",
    ).get.call(fakeThis);
}

function getSelectedExtraOptions(fakeThis) {
    return Object.getOwnPropertyDescriptor(
        AccountReportFilters.prototype,
        "selectedExtraOptions",
    ).get.call(fakeThis);
}

test("filterExtraOptionsData exposes the cash basis entry tied to show_cash_basis", () => {
    const shown = getFilterExtraOptionsData(fakeFilters({ showCashBasis: true }));
    expect(shown.report_cash_basis.show).toBe(true);
    expect(shown.report_cash_basis.group).toBe("account_user");

    const hidden = getFilterExtraOptionsData(fakeFilters({ showCashBasis: false }));
    expect(hidden.report_cash_basis.show).toBe(false);
});

test("selectedExtraOptions labels Cash Basis vs Accrual Basis", () => {
    expect(
        getSelectedExtraOptions(
            fakeFilters({ showCashBasis: true, reportCashBasis: true }),
        ),
    ).toBe("Cash Basis");

    expect(
        getSelectedExtraOptions(
            fakeFilters({ showCashBasis: true, reportCashBasis: false }),
        ),
    ).toBe("Accrual Basis");
});

test("selectedExtraOptions omits the cash basis label when the toggle is hidden", () => {
    expect(
        getSelectedExtraOptions(
            fakeFilters({ showCashBasis: false, reportCashBasis: true }),
        ),
    ).toBe("");
});
