/** @odoo-module native */
import "@hr_payroll/js/tours/hr_payroll";

import { markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { ICON_SELECTOR } from "@web/core/utils/icons";
import { patch } from "@web/core/utils/patch";

patch(registry.category("web_tour.tours").get("payroll_tours"), {
    steps() {
        const originalSteps = super.steps();
        const payrollStartStepIndex = originalSteps.findIndex(
            (step) => step.id === "hr_payroll_start",
        );
        originalSteps.splice(
            payrollStartStepIndex + 1,
            0,
            {
                trigger: `div[name='hr_responsible_id'] input`,
                content: markup(
                    _t("Select an <strong>HR Responsible</strong> for the contract."),
                ),
                tooltipPosition: "bottom",
                run: "click",
            },
            {
                isActive: ["auto"],
                trigger: `.ui-autocomplete > li > a:not(:has(${ICON_SELECTOR}))`,
                run: "click",
            },
        );
        return originalSteps;
    },
});
