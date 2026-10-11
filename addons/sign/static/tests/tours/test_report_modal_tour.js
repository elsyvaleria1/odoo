import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("sign_report_modal_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            content: "Open Sign app",
            trigger: '.o_app[data-menu-xmlid="sign.menu_document"]',
            run: "click",
        },
        ...stepUtils.goToMenuSteps(
            "sign.sign_reports",
            "sign.sign_report_green_savings",
            "Open Green Savings Report",
        ),
        {
            trigger:
                ':iframe body.o_in_iframe .green-savings-page a[data-bs-target=".modal_green_savings"]',
        },
        {
            content: "Open the modal",
            trigger: ':iframe a:contains("How are these results calculated?")',
            run: "click",
        },
        {
            trigger: ":iframe .modal_green_savings.show",
        },
    ],
});
