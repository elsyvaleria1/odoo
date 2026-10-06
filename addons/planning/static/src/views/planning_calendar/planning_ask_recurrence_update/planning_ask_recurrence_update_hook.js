/** @odoo-module native */
import { askRecurrenceUpdate } from "@resource/recurrence/ask_recurrence_update_dialog";
import { _t } from "@web/core/translation";

export function planningAskRecurrenceUpdate(dialogService) {
    return askRecurrenceUpdate(dialogService, {
        title: _t("Edit Recurrent Shift"),
        choices: {
            this: _t("This shift"),
            subsequent: _t("This and following shifts"),
            all: _t("All shifts"),
        },
    });
}
