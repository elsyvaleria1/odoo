/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { FileUploader } from "@web/core/file_upload";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

export class NewLoanComponent extends Component {
    static template = "account_loans.NewLoan";
    static components = {
        FileUploader,
    };
    static props = { ...standardWidgetProps, record: t.object().optional() };
    // base_import reads these and nothing else; without it FileUploader falls
    // back to accept="*" and hands unreadable files to the importer.
    static acceptedFileExtensions = ".csv,.ods,.xls,.xlsm,.xlsx";
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.acceptedFileExtensions = NewLoanComponent.acceptedFileExtensions;
    }

    /**
     * Persist the loan being edited and return its id.
     *
     * Guarding the save on `data.name` made the outcome depend on whether the
     * name field had been committed: type a name, upload without leaving the
     * field, and the record was still unsaved, so `resId` was false and the
     * server created a *second* loan named after the file. Saving
     * unconditionally raises the ordinary required-field error instead.
     */
    async saveLoan() {
        await this.props.record.model.root.save({ reload: false });
        return this.props.record.resId;
    }

    async onFileUploaded(file) {
        const loanId = await this.saveLoan();
        const [attachmentId] = await this.orm.create("ir.attachment", [
            {
                name: file.name,
                mimetype: file.type,
                datas: file.data,
            },
        ]);
        const action = await this.orm.call(
            "account.loan",
            "action_upload_amortization_schedule",
            [loanId, attachmentId],
        );
        this.action.doAction(action);
    }

    async openComputeWizard() {
        const loanId = await this.saveLoan();
        const action = await this.orm.call(
            "account.loan",
            "action_view_compute_wizard",
            [loanId],
        );
        this.action.doAction(action);
    }
}

export const newLoan = {
    component: NewLoanComponent,
};

registry.category("view_widgets").add("new_loan", newLoan);
