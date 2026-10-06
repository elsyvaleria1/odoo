/** @odoo-module native */
import { EmployeeDeclarationListView } from "@hr_payroll/views/employee_declaration_list/hr_payroll_employee_declaration_list_view";
import { registry } from "@web/core/registry";

import { DocumentsEmployeeDeclarationListController } from "./document_hr_payroll_employee_declaration_list_controller.js";

export const DocumentsEmployeeDeclarationListView = {
    ...EmployeeDeclarationListView,
    Controller: DocumentsEmployeeDeclarationListController,
};

registry
    .category("views")
    .add("employee_declaration_list", DocumentsEmployeeDeclarationListView, {
        force: true,
    });
