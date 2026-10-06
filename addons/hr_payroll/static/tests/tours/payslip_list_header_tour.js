import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("hr_payroll_payslip_list_header_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            content: "Open Payroll",
            trigger:
                '.o_app[data-menu-xmlid="hr_work_entry_enterprise.menu_hr_payroll_root"]',
            run: "click",
        },
        {
            content: "Open the Payslips menu",
            trigger: '[data-menu-xmlid="hr_payroll.menu_hr_payroll_payslips"]',
            run: "click",
        },
        {
            content: "Open All Payroll",
            trigger: '[data-menu-xmlid="hr_payroll.menu_hr_payroll_employee_payslips"]',
            run: "click",
        },
        {
            content: "Select the payslip that is still a draft",
            trigger:
                ".o_data_row:contains('Probe Draftee') .o_list_record_selector input:enabled",
            run: "click",
        },
        {
            content: "Select the payslip that is already confirmed",
            trigger:
                ".o_data_row:contains('Probe Confirmee') .o_list_record_selector input:enabled",
            run: "click",
        },
        {
            content: "The panel is rendering selection buttons",
            trigger: ".o_control_panel button:contains('Compute Sheet')",
        },
        {
            content:
                "Validate is offered: action_validate filters to the drafts, so it does " +
                "the right thing on a draft + confirmed selection",
            trigger: ".o_control_panel button:contains('Validate')",
        },
        {
            content:
                "Mark as Paid is withheld: action_payslip_paid raises unless every " +
                "selected payslip is already confirmed",
            trigger: ".o_control_panel:not(:has(button:contains('Mark as Paid')))",
        },
    ],
});
