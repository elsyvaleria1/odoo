import { mailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { AccountReportFilters } from "@report_formula/components/account_report/filters/filters";
import {
    contains,
    defineModels,
    makeMockEnv,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";

defineModels(mailModels);

test("can change the date filter by editing textually", async () => {
    const date = {
        filter: "this_month",
        mode: "range",
        period_type: "month",
    };

    const env = await makeMockEnv({
        controller: {
            filters: {
                show_period_comparison: false,
            },
            userGroups: {},
            cachedUserGroups: {},
            incrementCallNumber: (cacheKey) => {},
            cachedFilterOptions: {
                available_horizontal_groups: [],
                available_variants: [],
                companies: [],
                date: date,
                rounding_unit: "decimals",
                rounding_unit_names: {
                    decimals: ".$",
                },
            },
            reload: (optionPath, newOptions) => {
                expect.step(`reload ${optionPath} to ${newOptions}`);
            },
            updateOption: (option, value) => {
                expect.step(`update option ${option} to ${value}`);
                if (option === "date.filter") {
                    date.filter = value;
                    date.period_type = value.split("_")[1];
                }
            },
            revision: 0,
        },
        template: (name) => "report_formula.AccountReportFiltersCustomizable",
        component: (name) => AccountReportFilters,
    });

    const filters = await mountWithCleanup(AccountReportFilters, { env });

    await contains("#filter_date > button.o-dropdown").click();

    await contains(".date_filter_month.selected .input_current_date").click();
    await contains(".date_filter_month .input_current_date:not([readonly])").edit(
        "May 2020",
        {
            confirm: "tab",
        },
    );
    await contains(".date_filter_month.selected .input_current_date").click();
    await contains(".date_filter_month .input_current_date:not([readonly])").edit(
        "May 2018",
        {
            confirm: "tab",
        },
    );
    await contains(".date_filter_month.selected .input_current_date").click();
    await contains(".date_filter_month .input_current_date:not([readonly])").edit(
        "Invalid Month",
        {
            confirm: "tab",
        },
    );

    await contains(".date_filter_quarter").click();
    filters.__owl__.render();

    await contains(".date_filter_quarter.selected .input_current_date").click();
    await contains(".date_filter_quarter .input_current_date:not([readonly])").edit(
        "Apr - Jun 2020",
        { confirm: "tab" },
    );
    await contains(".date_filter_quarter.selected .input_current_date").click();
    await contains(".date_filter_quarter .input_current_date:not([readonly])").edit(
        "Apr - Jun 2018",
        { confirm: "tab" },
    );
    await contains(".date_filter_quarter.selected .input_current_date").click();
    await contains(".date_filter_quarter .input_current_date:not([readonly])").edit(
        "Random - Feb 2018",
        { confirm: "tab" },
    );
    await contains(".date_filter_quarter.selected .input_current_date").click();
    await contains(".date_filter_quarter .input_current_date:not([readonly])").edit(
        "Invalid Quarter",
        { confirm: "tab" },
    );

    await contains(".date_filter_year").click();
    filters.__owl__.render();

    await contains(".date_filter_year.selected .input_current_date").click();
    await contains(".date_filter_year .input_current_date:not([readonly])").edit(
        "2021",
        {
            confirm: "tab",
        },
    );
    await contains(".date_filter_year.selected .input_current_date").click();
    await contains(".date_filter_year .input_current_date:not([readonly])").edit(
        "2018",
        {
            confirm: "tab",
        },
    );
    await contains(".date_filter_year.selected .input_current_date").click();
    await contains(".date_filter_year .input_current_date:not([readonly])").edit(
        "Invalid Year",
        {
            confirm: "tab",
        },
    );

    expect.verifySteps([
        "update option date.filter to next_month",
        "update option date.period to 14",

        "update option date.filter to previous_month",
        "update option date.period to -10",

        "update option date.filter to this_quarter",
        "update option date.period to 0",

        "update option date.filter to next_quarter",
        "update option date.period to 5",

        "update option date.filter to previous_quarter",
        "update option date.period to -3",

        "update option date.filter to previous_quarter",
        "update option date.period to -4",

        "update option date.filter to this_year",
        "update option date.period to 0",

        "update option date.filter to next_year",
        "update option date.period to 2",

        "update option date.filter to previous_year",
        "update option date.period to -1",
    ]);
});
