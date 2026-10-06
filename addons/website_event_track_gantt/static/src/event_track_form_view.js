/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { ConfirmationDialog } from "@web/ui/dialog";
import { FormController, formView } from "@web/views/form";

export class EventTrackFormController extends FormController {
    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name === "unlink") {
            const canProceed = await new Promise((resolve) => {
                this.dialogService.add(ConfirmationDialog, {
                    body: _t("Are you sure you want to delete this track?"),
                    cancel: () => resolve(false),
                    close: () => resolve(false),
                    confirm: () => resolve(true),
                });
            });
            if (!canProceed) {
                return false;
            }
        }
        return super.beforeExecuteActionButton(clickParams);
    }
}

registry.category("views").add("event_track_form_in_gantt", {
    ...formView,
    Controller: EventTrackFormController,
});
