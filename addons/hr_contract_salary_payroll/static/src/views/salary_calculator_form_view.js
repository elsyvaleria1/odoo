/** @odoo-module native */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form";

import { SalaryCalculatorFormController } from "./salary_calculator_form_controller.js";

export const SalaryCalculatorFormView = {
    ...formView,
    Controller: SalaryCalculatorFormController,
};

registry.category("views").add("salary_calculator_form_view", SalaryCalculatorFormView);
