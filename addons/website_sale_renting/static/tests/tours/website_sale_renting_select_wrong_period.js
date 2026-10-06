import { formatValue, now, withWeekday } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";

function getValidNextStartDatetime() {
    return formatValue(withWeekday(now().add({ weeks: 1 }), 1), "D TT");
}

function getValidNextEndDatetime() {
    return formatValue(withWeekday(now().add({ weeks: 1 }), 3), "D TT");
}

registry.category("web_tour.tours").add("website_sale_renting_select_wrong_period", {
    url: "/shop?search=Computer",
    steps: () => [
        {
            content: "Select Computer",
            trigger: '.oe_product_cart:first a:contains("Computer")',
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "Wait for the daterange picker to be initialized",
            trigger: ".o_daterange_picker[data-has-default-dates]",
        },
        {
            content: "Pick an invalid start date",
            trigger: "input[name=renting_start_date]",
            run: "edit 01/01/2000 && press Tab",
        },
        {
            content: "Check that css_not_available has been added to the product form",
            trigger: "form.css_not_available",
        },
        {
            content:
                "Pick a valid end date first (otherwise start date after end date)",
            trigger: "input[name=renting_end_date]",
            run: `edit ${getValidNextEndDatetime()} && press Tab`,
        },
        {
            content: "Pick a valid start date",
            trigger: "input[name=renting_start_date]",
            run: `edit ${getValidNextStartDatetime()} && press Tab`,
        },
        {
            content: "Check that css_not_available has been removed",
            trigger: "form:not(.css_not_available)",
        },
    ],
});
