import { expect, test } from "@odoo/hoot";
import { AccountReportFilters } from "@report_formula/components/account_report/filters/filters";

function periodOf(date, startMonth, startDay, monthsPerPeriod) {
    const [start, end] = AccountReportFilters.prototype._computeReturnPeriodDates(
        {
            start_month: startMonth,
            start_day: startDay,
            months_per_period: monthsPerPeriod,
        },
        Temporal.PlainDate.from(date),
    );
    return [start.toString(), end.toString()];
}

test("return periods match the server's boundaries", () => {
    expect(periodOf("2025-02-15", 1, 31, 1)).toEqual(["2025-01-31", "2025-02-27"]);
    expect(periodOf("2025-02-28", 1, 31, 1)).toEqual(["2025-02-28", "2025-03-30"]);
    expect(periodOf("2023-05-10", 2, 29, 3)).toEqual(["2023-02-28", "2023-05-28"]);
    expect(periodOf("2025-05-10", 1, 1, 3)).toEqual(["2025-04-01", "2025-06-30"]);
    expect(periodOf("2025-02-10", 4, 1, 12)).toEqual(["2024-04-01", "2025-03-31"]);
});
