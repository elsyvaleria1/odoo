/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { SpreadsheetSelectorPanel } from "@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/spreadsheet_selector_panel";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

export class DocumentSelectorDialog extends Component {
    static template = "spreadsheet_dashboard_document.DocumentSelectorDialog";
    static components = { Dialog, SpreadsheetSelectorPanel };
    static props = { close: t.function(), dashboardGroupId: t.number() };
    props = useProps(this.constructor.props);

    setup() {
        this.notification = useService("notification");
        this.selectedSpreadsheet = null;
        this.orm = useService("orm");
        this.actionService = useService("action");
    }

    onSpreadsheetSelected({ spreadsheet }) {
        this.selectedSpreadsheet = spreadsheet;
    }

    async _confirm() {
        if (this.selectedSpreadsheet) {
            await this.orm.call(
                "spreadsheet.dashboard",
                "add_document_spreadsheet_to_dashboard",
                [this.props.dashboardGroupId, this.selectedSpreadsheet.id],
            );
            this.actionService.switchView("form", {
                resId: this.props.dashboardGroupId,
            });
            this.notification.add(
                _t(
                    "We're sending the original spreadsheet to the trash. No worries, though! You can still make edits by heading over to the Dashboard configuration.",
                ),
                { type: "warning", sticky: true },
            );
        } else {
            const action = await this.orm.call(
                "spreadsheet.dashboard",
                "action_view_new_dashboard",
                [this.props.dashboardGroupId],
            );
            this.actionService.doAction(action);
        }
        this.props.close();
    }

    _cancel() {
        this.props.close();
    }
}
