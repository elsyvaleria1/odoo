/** @odoo-module native */
import { ExportAuditReportToPDFDialog } from "@accountant_knowledge/components/export_audit_report_to_pdf_dialog/export_audit_report_to_pdf_dialog";
import { OptionsDropdown } from "@knowledge/components/options_dropdown/options_dropdown";
import { patch } from "@web/core/utils/patch";

patch(OptionsDropdown.prototype, {
    exportAuditReportToPDF() {
        this.dialog.add(ExportAuditReportToPDFDialog, {
            record: this.props.record,
        });
    },
});
