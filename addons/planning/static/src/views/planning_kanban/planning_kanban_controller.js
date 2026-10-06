/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { AddressRecurrencyConfirmationDialog } from "@planning/components/address_recurrency_confirmation_dialog/address_recurrency_confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { KanbanController } from "@web/views/kanban";

import { usePlanningRecurringDeleteAction } from "../planning_hooks.js";

export class PlanningKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.dialogService = useService("dialog");
        this.state = proxy({
            recurrenceUpdate: "this",
        });
        this.planningRecurrenceDeletion = usePlanningRecurringDeleteAction();
    }

    get modelOptions() {
        return {
            ...super.modelOptions,
            lazy: false,
        };
    }

    async deleteRecord(record) {
        if (record.data.repeat) {
            this.dialogService.add(AddressRecurrencyConfirmationDialog, {
                confirm: async () => {
                    await this.planningRecurrenceDeletion._actionAddressRecurrency(
                        record,
                        this.state.recurrenceUpdate,
                    );
                    await this.model.root.deleteRecords([record]);
                },
                onChangeRecurrenceUpdate:
                    this.planningRecurrenceDeletion._setRecurrenceUpdate.bind(this),
                selected: this.state.recurrenceUpdate,
            });
        } else {
            super.deleteRecord(record);
        }
    }
}
