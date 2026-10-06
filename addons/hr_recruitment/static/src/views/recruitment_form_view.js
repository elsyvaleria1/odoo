/** @odoo-module native */
import { RecruitmentFormController } from "@hr_recruitment/views/recruitment_form_controller";
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form";

export const RecruitmentFormView = {
    ...formView,
    Controller: RecruitmentFormController,
};

registry.category("views").add("recruitment_form_view", RecruitmentFormView);
