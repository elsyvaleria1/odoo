/** @odoo-module native */
import { provideSpreadsheetEnv } from "@spreadsheet/hooks";
import { AbstractSpreadsheetAction } from "@spreadsheet_edition/bundle/actions/abstract_spreadsheet_action";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";

const log = makeLogger("spreadsheet_dashboard_edition.action");

export class DashboardEditAction extends AbstractSpreadsheetAction {
    static template = "spreadsheet_dashboard_edition.DashboardEditAction";

    resModel = "spreadsheet.dashboard";
    threadField = "dashboard_id";

    setup() {
        super.setup();
        provideSpreadsheetEnv({
            makeCopy: this.makeCopy.bind(this),
            onSpreadsheetShared: this.shareSpreadsheet.bind(this),
            isDashboardPublished: () => this.data && this.data.is_published,
            toggleDashboardPublished: this.togglePublished.bind(this),
            isRecordReadonly: () => this.data && this.data.isReadonly,
        });
    }

    togglePublished(is_published) {
        log.logic("togglePublished", { dashboardId: this.resId, is_published });
        this.orm.write("spreadsheet.dashboard", [this.resId], {
            is_published,
        });
    }

    async shareSpreadsheet(data, excelExport) {
        log.logic("shareSpreadsheet", () => ({
            dashboardId: this.resId,
            excelFiles: excelExport.files.length,
        }));
        const url = await this.orm.call(
            "spreadsheet.dashboard.share",
            "action_get_share_url",
            [
                {
                    dashboard_id: this.resId,
                    spreadsheet_data: JSON.stringify(data),
                    excel_files: excelExport.files,
                },
            ],
        );
        return url;
    }
}

registry
    .category("actions")
    .add("action_edit_dashboard", DashboardEditAction, { force: true });
