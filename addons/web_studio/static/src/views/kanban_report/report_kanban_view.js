/** @odoo-module native */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KanbanController, kanbanView } from "@web/views/kanban";

import { NewReportDialog } from "./new_report_dialog.js";

class StudioReportKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.studio = useService("studio");
        this.dialogService = useService("dialog");
        this.orm = useService("orm");
    }
    createRecord() {
        this.dialogService.add(NewReportDialog, {
            resModel: this.props.context.default_model,
            onReportCreated: (report) => {
                this.openRecord({ data: report, resId: report.id });
            },
        });
    }

    openRecord(record) {
        return this.studio.setParams({
            editedReport: { data: record.data, res_id: record.resId },
        });
    }
}

const studioReportKanbanView = {
    ...kanbanView,
    Controller: StudioReportKanbanController,
};

registry.category("views").add("studio_report_kanban", studioReportKanbanView);
