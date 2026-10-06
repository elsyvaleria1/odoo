import { mailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { AccountReportFilters } from "@report_formula/components/account_report/filters/filters";
import {
    defineModels,
    makeMockEnv,
    mountWithCleanup,
    serverState,
} from "@web/../tests/web_test_helpers";

defineModels(mailModels);

async function mountFilters() {
    const env = await makeMockEnv({
        controller: {
            filters: { show_period_comparison: false },
            userGroups: {},
            cachedUserGroups: {},
            incrementCallNumber: () => {},
            cachedFilterOptions: {
                available_horizontal_groups: [],
                available_variants: [],
                companies: [],
                date: { filter: "this_month", mode: "range", period_type: "month" },
                rounding_unit: "decimals",
                rounding_unit_names: { decimals: ".$" },
            },
            reload: () => {},
            updateOption: () => {},
            revision: 0,
        },
        template: () => "report_formula.AccountReportFiltersCustomizable",
        component: () => AccountReportFilters,
    });
    await mountWithCleanup(AccountReportFilters, { env });
}

test("the report configuration button shows in debug mode", async () => {
    serverState.debug = "1";
    await mountFilters();
    expect("#filter_configuration").toHaveCount(1);
});

test("the report configuration button hides outside debug mode", async () => {
    await mountFilters();
    expect("#filter_configuration").toHaveCount(0);
});
