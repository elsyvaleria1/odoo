/** @odoo-module native */
import { RecruitmentActionHelper } from "@hr_recruitment/views/recruitment_helper_view";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";
import { KanbanRenderer, kanbanView } from "@web/views/kanban";

export class RecruitmentKanbanRenderer extends KanbanRenderer {
    static template = "hr_recruitment.RecruitmentKanbanRenderer";
    static components = {
        ...KanbanRenderer.components,
        RecruitmentActionHelper,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    async archiveRecord(record, active) {
        if (active && record.data.application_count > 0) {
            this.dialog.add(ConfirmationDialog, {
                body: _t(
                    "This job position and all related applicants will be archived. Are you sure?",
                ),
                confirmLabel: _t("Archive"),
                confirm: () => {
                    record.archive();
                    this.props.list.load();
                },
                cancel: () => {},
            });
        } else if (active) {
            record.archive();
            this.props.list.load();
        } else {
            record.unarchive();
            this.props.list.load();
        }
    }
}

export const RecruitmentKanbanView = {
    ...kanbanView,
    Renderer: RecruitmentKanbanRenderer,
};

registry.category("views").add("recruitment_kanban_view", RecruitmentKanbanView);
