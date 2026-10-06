/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class ExportAuditReportToPDFDialog extends Component {
    static template = "accountant_knowledge.ExportAuditReportToPDFDialog";
    static components = { Dialog };
    static props = { record: t.object(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.state = proxy({
            includePdfFiles: true,
            includeChildArticles: true,
        });
    }

    async exportAuditReportToPDF() {
        this.props.close();
        await this.action.doAction({
            type: "ir.actions.act_url",
            target: "download",
            url: `/knowledge_accountant/article/${this.props.record.resId}/audit_report?include_pdf_files=${this.state.includePdfFiles}&include_child_articles=${this.state.includeChildArticles}`,
        });
    }
}
