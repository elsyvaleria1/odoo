/** @odoo-module native */
import { Avatar } from "@mail/views/web/fields/avatar/avatar";
import { markup } from "@odoo/owl";
import { TaskGanttRendererCommon } from "@project_gantt/views/project_task_common/task_gantt_renderer_common";
import { SelectCreateAutoPlanDialog } from "@project_gantt/views/view_dialogs/select_auto_plan_create_dialog";
import { compareDates, toDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { FormViewDialog } from "@web/views/view_dialogs";

import { TaskGanttRendererControls } from "./task_gantt_renderer_controls.js";

const FINISH_ANCHORED_TYPES = ["fs", "ff"];
const START_CONSTRAINED_TYPES = ["fs", "ss"];

export class TaskGanttRenderer extends TaskGanttRendererCommon {
    static components = {
        ...TaskGanttRendererCommon.components,
        GanttRendererControls: TaskGanttRendererControls,
        Avatar,
    };
    setup() {
        super.setup(...arguments);
        this.notificationService = useService("notification");
        this.orm = useService("orm");
        useLayoutEffect(
            (el) => el.classList.add("o_project_gantt"),
            () => [this.gridRef.el],
        );
    }

    /**
     * @override
     */
    enrichPill(pill) {
        const enrichedPill = super.enrichPill(pill);
        if (
            this.props.model.highlightIds &&
            !this.props.model.highlightIds.includes(enrichedPill.record.id)
        ) {
            pill.className += " opacity-25";
        }
        return enrichedPill;
    }

    getDependencyLink(masterRecord, slaveRecord) {
        return (
            slaveRecord.gantt_dependency_types?.[masterRecord.id] ?? {
                type: "fs",
                lag: 0,
            }
        );
    }

    getConnectorAlert(masterRecord, slaveRecord) {
        if (
            !masterRecord.display_warning_dependency_in_gantt ||
            !slaveRecord.display_warning_dependency_in_gantt
        ) {
            return;
        }
        const { type, lag } = this.getDependencyLink(masterRecord, slaveRecord);
        if (type === "fs" && !lag) {
            return super.getConnectorAlert(...arguments);
        }
        const { dateStartField, dateStopField } = this.model.metaData;
        const shifted = (value) =>
            toDateTime(value).add({ seconds: Math.round(lag * 3600) });
        const anchorField = FINISH_ANCHORED_TYPES.includes(type)
            ? dateStopField
            : dateStartField;
        const constrainedField = START_CONSTRAINED_TYPES.includes(type)
            ? dateStartField
            : dateStopField;
        const constrained = toDateTime(slaveRecord[constrainedField]);
        if (compareDates(constrained, shifted(masterRecord[anchorField])) >= 0) {
            return null;
        }
        return compareDates(constrained, shifted(masterRecord[dateStartField])) < 0
            ? "error"
            : "warning";
    }

    generateConnectors() {
        super.generateConnectors();
        for (const [connectorId, { sourcePillId, targetPillId }] of Object.entries(
            this.mappingConnectorToPills,
        )) {
            const connector = this.connectors[connectorId];
            if (!connector || !sourcePillId || !targetPillId) {
                continue;
            }
            const { type } = this.getDependencyLink(
                this.pills[sourcePillId].record,
                this.pills[targetPillId].record,
            );
            if (type === "fs") {
                continue;
            }
            connector.sourcePoint = () =>
                this.getPoint(sourcePillId, FINISH_ANCHORED_TYPES.includes(type));
            connector.targetPoint = () =>
                this.getPoint(targetPillId, !START_CONSTRAINED_TYPES.includes(type));
        }
    }

    getSelectCreateDialogProps() {
        const props = super.getSelectCreateDialogProps(...arguments);
        const onCreateEdit = () => {
            this.dialogService.add(FormViewDialog, {
                context: props.context,
                resModel: props.resModel,
                onRecordSaved: async (record) => {
                    await record.save({ reload: false });
                    await this.model.fetchData();
                },
            });
        };
        const onSelectedAutoPlan = (resIds) => {
            props.context.smart_task_scheduling = true;
            if (resIds.length) {
                this.model.reschedule(
                    resIds,
                    props.context,
                    this.openPlanDialogCallback.bind(this),
                );
            }
        };
        props.onSelectedNoSmartSchedule = props.onSelected;
        props.onSelected = onSelectedAutoPlan;
        props.onCreateEdit = onCreateEdit;
        return props;
    }

    getNotificationOnSmartSchedule(notifText, old_vals_per_task_id, type) {
        this.closeNotificationFn?.();
        this.closeNotificationFn = this.notificationService.add(
            markup`<i class="fa-solid fa-check btn-link"></i><span class="ms-1">${notifText}</span>`,
            {
                type: type,
                sticky: true,
                buttons: [
                    {
                        name: "Undo",
                        icon: "fa-undo",
                        onClick: async () => {
                            const ids = Object.keys(old_vals_per_task_id).map(Number);
                            await this.orm.call(
                                "project.task",
                                "action_rollback_auto_scheduling",
                                [ids, old_vals_per_task_id],
                            );
                            this.closeNotificationFn();
                            await this.model.fetchData();
                        },
                    },
                ],
            },
        );
    }

    openPlanDialogCallback(res) {
        if (res && Array.isArray(res)) {
            const warnings = Object.entries(res[0]);
            const old_vals_per_task_id = res[1];
            const has_tasks_planned = Object.keys(old_vals_per_task_id).length > 0;
            const has_warnings = warnings.length > 0;

            if (!has_warnings && !has_tasks_planned) {
                return;
            }

            for (const warning of warnings) {
                this.notificationService.add(warning[1], {
                    type: "warning",
                    sticky: true,
                });
            }

            if (has_tasks_planned) {
                const notif_text = has_warnings
                    ? _t(
                          "Some tasks have been successfully scheduled for the upcoming periods. Some warnings were generated. Please review them for details.",
                      )
                    : _t(
                          "Tasks have been successfully scheduled for the upcoming periods.",
                      );
                const type = has_warnings ? "warning" : "success";
                this.getNotificationOnSmartSchedule(
                    notif_text,
                    old_vals_per_task_id,
                    type,
                );
            }
        }
    }

    getRowAvatar(row) {
        const { groupedByField, name, resId } = row;
        if (groupedByField === "user_ids" && Boolean(resId)) {
            const { fields } = this.model.metaData;
            return { resModel: fields.user_ids.relation, resId, displayName: name };
        }
        return null;
    }

    highlightPill(pillId, highlighted) {
        if (!this.connectorDragState.dragging) {
            return super.highlightPill(pillId, highlighted);
        }
        const pill = this.pills[pillId];
        if (!pill) {
            return;
        }
        const { record } = pill;
        if (!this.shouldRenderRecordConnectors(record)) {
            return super.highlightPill(pillId, false);
        }
        return super.highlightPill(pillId, highlighted);
    }

    onConnectorHover() {
        return !this.connectorDragState.dragging;
    }

    onPlan(rowId, columnStart, columnStop) {
        let { start, stop } = this.getColumnStartStop(columnStart, columnStop);
        ({ start, stop } = this.normalizeTimeRange(start, stop));
        this.dialogService.add(
            SelectCreateAutoPlanDialog,
            this.getSelectCreateDialogProps({ rowId, start, stop, withDefault: true }),
        );
    }

    getUndoAfterDragMessages(dragAction) {
        if (dragAction === "copy") {
            return {
                success: _t("Task duplicated"),
                undo: _t("Task removed"),
                failure: _t("Task could not be removed"),
            };
        }
        return {
            success: _t("Task rescheduled"),
            undo: _t("Task reschedule undone"),
            failure: _t("Failed to undo reschedule"),
        };
    }

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    /*
     * @overwrite
     */
    onRemoveButtonClick(connectorId) {
        const { sourcePillId, targetPillId } =
            this.mappingConnectorToPills[connectorId];
        this.highlightPill(sourcePillId, false);
        this.highlightPill(targetPillId, false);
        super.onRemoveButtonClick(connectorId);
    }
}
