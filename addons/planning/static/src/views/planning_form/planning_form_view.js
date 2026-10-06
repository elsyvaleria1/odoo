/** @odoo-module native */
import { markup, onMounted, proxy } from "@odoo/owl";
import { AddressRecurrencyConfirmationDialog } from "@planning/components/address_recurrency_confirmation_dialog/address_recurrency_confirmation_dialog";
import { compareDates, deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { FetchRecordError } from "@web/model/relational_model";
import { ConfirmationDialog } from "@web/ui/dialog";
import { FormController, formView } from "@web/views/form";
import { FormViewDialog } from "@web/views/view_dialogs";

import { usePlanningRecurringDeleteAction } from "../planning_hooks.js";

export class PlanningFormController extends FormController {
    setup() {
        super.setup();
        this.config = useViewConfig();
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = proxy({
            recurrenceUpdate: "this",
        });
        this.planningRecurrenceDeletion = usePlanningRecurringDeleteAction();
        onMounted(() => {
            this.initialTemplateCreation = this.model.root.data.template_creation;
        });
    }

    async saveButtonClicked(params = {}) {
        try {
            return await super.saveButtonClicked(params);
        } catch (error) {
            if (!(error instanceof FetchRecordError)) {
                throw error;
            }
            await this.model.root.discard();
            this.config.historyBack();
        }
        return false;
    }

    async onRecordSaved(record, changes) {
        if ("repeat" in changes && record.data["repeat"]) {
            const message = _t("Recurring shifts created");
            this.notification.add(
                markup`<i class="fa-solid fa-check"></i><span class="ms-1">${message}</span>`,
                { type: "success" },
            );
        }
        if (
            record.context.is_record_created &&
            (compareDates(
                deserializeDateTime(record.context.view_start_date),
                record.data.start_datetime,
            ) > 0 ||
                compareDates(
                    deserializeDateTime(record.context.view_end_date),
                    record.data.end_datetime,
                ) < 0)
        ) {
            this.notification.add(_t("The shift has successfully been created."), {
                type: "success",
            });
        }
    }

    async beforeExecuteActionButton(clickParams) {
        const shift = this.model.root;
        this.state.recurrenceUpdate = shift.data.recurrence_update;
        if (clickParams.name === "unlink") {
            const canProceed = await new Promise((resolve) => {
                if (shift.data.recurrency_id) {
                    this.dialogService.add(AddressRecurrencyConfirmationDialog, {
                        cancel: () => resolve(false),
                        close: () => resolve(false),
                        confirm: async () => {
                            await this.planningRecurrenceDeletion._actionAddressRecurrency(
                                shift,
                                this.state.recurrenceUpdate,
                            );
                            return resolve(true);
                        },
                        onChangeRecurrenceUpdate:
                            this.planningRecurrenceDeletion._setRecurrenceUpdate.bind(
                                this,
                            ),
                        selected: this.state.recurrenceUpdate,
                    });
                } else {
                    this.dialogService.add(ConfirmationDialog, {
                        body: _t("Are you sure you want to delete this shift?"),
                        confirmLabel: _t("Delete"),
                        cancel: () => resolve(false),
                        close: () => resolve(false),
                        confirm: () => resolve(true),
                    });
                }
            });
            if (!canProceed) {
                return false;
            }
        } else if (clickParams.name === "action_send") {
            if (shift.resId) {
                // We want to check if all employees impacted to this action have a email.
                // For those who do not have any email in work_email field, then a FormViewDialog is displayed for each employee who is not email.
                const result = await this.orm.call(
                    this.props.resModel,
                    "get_people_without_email",
                    [shift.resId],
                );
                if (result) {
                    const { res_ids: resIds, relation: resModel, context } = result;
                    const canProceed = await this.displayDialogWhenNoEmail(
                        resIds,
                        resModel,
                        context,
                    );
                    if (!canProceed) {
                        return false;
                    }
                }
            } else if (shift.data.resource_id && !shift.data.work_email) {
                const canProceed = await new Promise((resolve) => {
                    this.dialogService.add(
                        FormViewDialog,
                        {
                            title: "Add an email address",
                            resModel: "resource.resource",
                            resId: shift.data.resource_id.id,
                            context: {
                                form_view_ref:
                                    "planning.resource_resource_view_form_email",
                                force_email: true,
                            },
                            onRecordSaved: () => resolve(true),
                        },
                        { onClose: () => resolve(false) },
                    );
                });
                if (!canProceed) {
                    return false;
                }
            }
        }
        if (
            shift.data.allow_template_creation &&
            clickParams.name === "action_save_template"
        ) {
            // then the shift should be saved as a template too.
            const message = _t("Shift saved as template");
            this.notification.add(
                markup`<i class="fa-solid fa-check"></i><span class="ms-1">${message}</span>`,
                { type: "success" },
            );
        }
        return super.beforeExecuteActionButton(clickParams);
    }

    /**
     * Display a dialog form view of employee model for each employee who has no work email.
     *
     * @param {Array<number>} resIds the employee ids without work email.
     * @param {string} resModel the model name to display the form view.
     * @param {Object} context context.
     *
     * @returns {Promise}
     */
    async displayDialogWhenNoEmail(resIds, resModel, context) {
        const results = await Promise.all(
            resIds.map(
                (resId) =>
                    new Promise((resolve) => {
                        this.dialogService.add(
                            FormViewDialog,
                            {
                                title: "",
                                resModel,
                                resId,
                                context,
                                preventCreate: true,
                                onRecordSaved: () => resolve(true),
                            },
                            { onClose: () => resolve(false) },
                        );
                    }),
            ),
        );
        return results.every((r) => r);
    }

    async deleteRecord() {
        const shift = this.model.root;
        this.state.recurrenceUpdate = shift.data.recurrence_update;
        if (shift.data.recurrency_id) {
            this.dialogService.add(AddressRecurrencyConfirmationDialog, {
                confirm: async () => {
                    await this.planningRecurrenceDeletion._actionAddressRecurrency(
                        shift,
                        this.state.recurrenceUpdate,
                    );
                    await shift.delete().then(
                        () => {
                            if (!shift.resId) {
                                this.config.historyBack();
                            }
                        },
                        () => {
                            this.config.historyBack();
                        },
                    );
                },
                onChangeRecurrenceUpdate:
                    this.planningRecurrenceDeletion._setRecurrenceUpdate.bind(this),
                selected: this.state.recurrenceUpdate,
            });
        } else {
            await super.deleteRecord(...arguments);
        }
    }
}

export const planningFormView = {
    ...formView,
    Controller: PlanningFormController,
};

registry.category("views").add("planning_form", planningFormView);
