/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { AddressRecurrencyConfirmationDialog } from "@planning/components/address_recurrency_confirmation_dialog/address_recurrency_confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list";

import { usePlanningRecurringDeleteAction } from "../planning_hooks.js";

export class PlanningTreeController extends ListController {
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

    async onDeleteSelectedRecords() {
        const selectedRecords = this.model.root.selection;
        const recordsWithRecurrency_id = selectedRecords.filter(
            (record) => record.data.recurrency_id,
        );
        if (recordsWithRecurrency_id.length > 0) {
            this.dialogService.add(AddressRecurrencyConfirmationDialog, {
                confirm: async () => {
                    await this.planningRecurrenceDeletion._actionAddressRecurrency(
                        {
                            resId: recordsWithRecurrency_id.map(
                                (record) => record.resId,
                            ),
                            resModel: this.props.resModel,
                        },
                        this.state.recurrenceUpdate,
                    );
                    await this.model.root.deleteRecords();
                },
                onChangeRecurrenceUpdate:
                    this.planningRecurrenceDeletion._setRecurrenceUpdate.bind(this),
                selected: this.state.recurrenceUpdate,
            });
        } else {
            await super.onDeleteSelectedRecords();
        }
    }
}
