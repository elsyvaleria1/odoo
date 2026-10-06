/** @odoo-module native */
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list";

export class EmployeeDeclarationListController extends ListController {
    static template = "hr_payroll.EmployeeDeclarationListController";

    setup() {
        super.setup();
        this.dialogContext = useDialogContext();
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.action = useService("action");
    }

    getNumberToGenerate() {
        return this.onlyDrafts()
            ? ""
            : this.model.root.selection.filter((r) => r.data.state === "draft").length;
    }

    noDrafts() {
        if (this.hasSelectedRecords) {
            return (
                this.model.root.selection.filter((r) => r.data.state === "draft")
                    .length < 1
            );
        }
        return (
            this.model.root.records.filter((r) => r.data.state === "draft").length < 1
        );
    }

    onlyDrafts() {
        if (this.hasSelectedRecords) {
            if (
                this.model.root.selection.filter((r) => r.data.state === "draft")
                    .length === this.model.root.selection.length
            ) {
                return true;
            }
        }
        return (
            this.model.root.records.filter((r) => r.data.state === "draft").length ===
            this.model.root.records.length
        );
    }

    checkOnlyDrafts() {
        return this.onlyDrafts() ? "btn-primary" : "btn-secondary";
    }

    generatePdfs() {
        const records = this.hasSelectedRecords
            ? this.model.root.selection
            : this.model.root.records;
        return this.action.doActionButton({
            type: "object",
            resModel: "hr.payroll.employee.declaration",
            name: "action_generate_pdf",
            resIds: records.filter((r) => r.data.state === "draft").map((r) => r.resId),
        });
    }
}
