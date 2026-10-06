/** @odoo-module native */
import { EmployeeDeclarationListController } from "@hr_payroll/views/employee_declaration_list/hr_payroll_employee_declaration_list_controller";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { useService } from "@web/core/utils/hooks";

export class DocumentsEmployeeDeclarationListController extends EmployeeDeclarationListController {
    static template = "document_hr_payroll.DocumentsEmployeeDeclarationListController";

    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.ui = useService("ui");
    }

    generatedRecords(records) {
        return records.filter((r) => r.data.state === "pdf_generated");
    }

    targetRecords() {
        return this.hasSelectedRecords
            ? this.model.root.selection
            : this.model.root.records;
    }

    getNumberToPost() {
        return this.onlyGenerated()
            ? ""
            : this.generatedRecords(this.targetRecords()).length;
    }

    noGenerated() {
        if (this.hasSelectedRecords) {
            return this.generatedRecords(this.model.root.selection).length < 1;
        }
        return this.generatedRecords(this.model.root.records).length < 1;
    }

    onlyGenerated() {
        if (this.hasSelectedRecords) {
            if (
                this.generatedRecords(this.model.root.selection).length ===
                this.model.root.selection.length
            ) {
                return true;
            }
        }
        return (
            this.generatedRecords(this.model.root.records).length ===
            this.model.root.records.length
        );
    }

    checkOnlyGenerated() {
        return this.onlyGenerated() ? "btn-primary" : "btn-secondary";
    }

    postPdfs() {
        return this.action.doActionButton({
            type: "object",
            resModel: "hr.payroll.employee.declaration",
            name: "action_post_in_documents",
            resIds: this.generatedRecords(this.targetRecords()).map((r) => r.resId),
        });
    }
}
