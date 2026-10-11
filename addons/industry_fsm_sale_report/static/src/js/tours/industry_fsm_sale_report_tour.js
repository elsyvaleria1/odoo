/** @odoo-module native */

import "@industry_fsm/js/tours/industry_fsm_tour";

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

patch(registry.category("web_tour.tours").get("industry_fsm_tour"), {
    steps() {
        const originalSteps = super.steps();
        const fsmStartStepIndex = originalSteps.findIndex(
            (step) => step.id === "industry_fsm_sale_sign_send_start",
        );
        const fsmStopStepIndex = originalSteps.findIndex(
            (step) => step.id === "industry_fsm_sale_sign_send_end",
        );
        originalSteps.splice(
            fsmStartStepIndex,
            fsmStopStepIndex - fsmStartStepIndex + 1,
        );
        return originalSteps;
    },
});
