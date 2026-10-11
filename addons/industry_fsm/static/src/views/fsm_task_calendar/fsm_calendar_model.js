/** @odoo-module native */
import { ProjectTaskCalendarModel } from "@project/views/project_task_calendar/project_task_calendar_model";
import { serializeDateTime } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

export class FsmTaskCalendarModel extends ProjectTaskCalendarModel {
    setup() {
        super.setup(...arguments);
        this.meta.scale = this.viewContext.isSmall ? "day" : this.meta.scale;
    }

    _getPlanTaskVals(taskToPlan, date, timeSlotSelected = false) {
        const planTaskVals = super._getPlanTaskVals(...arguments);
        if (!timeSlotSelected) {
            const [start, end] = this.getAllDayDates(date, date);
            planTaskVals["date_start"] = serializeDateTime(start);
            planTaskVals["date_end"] = serializeDateTime(end);
        }
        return planTaskVals;
    }

    _getPlanTaskContext(taskToPlan, timeSlotSelected) {
        const context = super._getPlanTaskContext(...arguments);
        if (!timeSlotSelected) {
            context.task_calendar_plan_full_day = true;
        }
        return context;
    }

    planStartsAtCalendarClick() {
        return true;
    }
}

patch(ProjectTaskCalendarModel.prototype, {
    get tasksToPlanSpecification() {
        const tasksToPlanSpecification = super.tasksToPlanSpecification;
        tasksToPlanSpecification["is_fsm"] = {};
        return tasksToPlanSpecification;
    },

    _getPlanTaskVals(taskToPlan, date, timeSlotSelected = false) {
        const planTaskVals = super._getPlanTaskVals(...arguments);
        if (!timeSlotSelected && taskToPlan.is_fsm) {
            const [start, end] = this.getAllDayDates(date, date);
            planTaskVals["date_start"] = serializeDateTime(start);
            planTaskVals["date_end"] = serializeDateTime(end);
        }
        return planTaskVals;
    },

    _getPlanTaskContext(taskToPlan, timeSlotSelected) {
        const context = super._getPlanTaskContext(...arguments);
        if (taskToPlan.is_fsm && !timeSlotSelected) {
            context.task_calendar_plan_full_day = true;
        }
        return context;
    },
});
