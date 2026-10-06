/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { EmployeeDeclarationListController } from "./hr_payroll_employee_declaration_list_controller.js";

export const EmployeeDeclarationListView = Object.assign({}, listView, {
    ...listView,
    Controller: EmployeeDeclarationListController,
});

registry
    .category("views")
    .add("employee_declaration_list", EmployeeDeclarationListView);
