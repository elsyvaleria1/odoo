/** @odoo-module native */

import { useTimeOffContext } from "@hr_holidays/views/time_off_context";
import { fromJSDate, toISODate } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useOwnedDialogs, useService } from "@web/core/utils/hooks";

import { AllocationFormViewDialog } from "./view_dialog/allocation_form_view_dialog.js";

export function formatNumber(lang, number, maxDecimals = 2) {
    const numberFormat = new Intl.NumberFormat(lang, {
        maximumFractionDigits: maxDecimals,
    });
    return numberFormat.format(number);
}

export function useMandatoryDays(props) {
    return (info) => {
        const date = toISODate(fromJSDate(info.date));
        const mandatoryDay = props.model.mandatoryDays[date];
        if (mandatoryDay) {
            return ["hr_mandatory_day", `hr_mandatory_day_${mandatoryDay}`];
        }
        return [];
    };
}

export function useLeaveCancelWizard() {
    const action = useService("action");

    return (leaveId, callback) => {
        action.doAction(
            {
                name: _t("Cancel Time Off"),
                type: "ir.actions.act_window",
                res_model: "wizard.hr.leave.cancel",
                target: "new",
                views: [[false, "form"]],
                context: {
                    dialog_size: "medium",
                    default_leave_id: leaveId,
                },
            },
            {
                onClose: callback,
            },
        );
    };
}

export function useNewAllocationRequest() {
    const addDialog = useOwnedDialogs();
    const env = {
        timeOffBus: useTimeOffContext().timeOffBus,
    };
    return async (employeeId, holidayStatusId) => {
        let size = "md";
        const context = {
            form_view_ref: "hr_holidays.hr_leave_allocation_view_form_dashboard",
        };
        if (employeeId) {
            size = "lg";
            context["default_employee_id"] = employeeId;
            context["form_view_ref"] =
                "hr_holidays.hr_leave_allocation_view_form_manager_dashboard";
        }
        if (holidayStatusId) {
            context["default_holiday_status_id"] = holidayStatusId;
        }
        addDialog(AllocationFormViewDialog, {
            resModel: "hr.leave.allocation",
            title: _t("New Allocation"),
            context: context,
            size: size,
            onRecordSaved: () => {
                env.timeOffBus.trigger("update_dashboard");
            },
        });
    };
}
