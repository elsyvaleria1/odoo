/** @odoo-module native */
import { formatNumber, useNewAllocationRequest } from "@hr_holidays/views/hooks";
import { Component, t, useProps } from "@odoo/owl";
import { serializeDate, today as currentDay } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover";

export class TimeOffCardPopover extends Component {
    static template = "hr_holidays.TimeOffCardPopover";
    static props = {
        allocated: t.any(),
        accrual_bonus: t.any(),
        approved: t.any(),
        planned: t.any(),
        left: t.any(),
        warning: t.any(),
        closest: t.any(),
        request_unit: t.any(),
        exceeding_duration: t.any(),
        close: t.any().optional(),
        allows_negative: t.any(),
        max_allowed_negative: t.any(),
        onClickNewAllocationRequest: t.any().optional(),
        errorLeaves: t.any(),
        accrualExcess: t.any(),
        timeOffType: t.any(),
        employeeId: t.any(),
        employeeCompany: t.any(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.actionService = useService("action");
    }

    async openLeaves() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.leave",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [["id", "in", this.props.errorLeaves]],
        });
    }

    async allocatedLeaves() {
        const { employeeId, timeOffType, employeeCompany } = this.props;
        const today = serializeDate(currentDay());
        const isInHolidaysUserGroup = await user.hasGroup(
            "hr_holidays.group_hr_holidays_user",
        );

        const resModel = "hr.leave.allocation";
        const name = _t("My Allocations");
        const context = isInHolidaysUserGroup
            ? {}
            : {
                  list_view_ref: "hr_holidays.hr_leave_allocation_view_tree_my",
                  form_view_ref: "hr_holidays.hr_leave_allocation_view_form",
              };
        const domain = [
            ["holiday_status_id", "=", timeOffType],
            ["employee_company_id", "=", employeeCompany],
            "|",
            ["date_to", "=", false],
            ["date_to", ">=", today],
            employeeId
                ? ["employee_id", "=", employeeId]
                : ["employee_id.user_id", "=", user.userId],
        ];

        openLeaveWindow(this.actionService, resModel, name, domain, context);
    }

    async navigateInfo(stateList) {
        const { employeeId, timeOffType, employeeCompany } = this.props;
        const isInHolidaysUserGroup = await user.hasGroup(
            "hr_holidays.group_hr_holidays_user",
        );

        const resModel = "hr.leave";
        const name = _t("My Time Off");
        const domain = [
            ["state", "in", stateList],
            ["holiday_status_id", "=", timeOffType],
            ["company_id", "=", employeeCompany],
            employeeId
                ? ["employee_id", "=", employeeId]
                : ["user_id", "=", user.userId],
        ];
        const context = isInHolidaysUserGroup
            ? {
                  search_default_group_date_from: true,
              }
            : {
                  search_default_group_date_from: true,
                  list_view_ref: "hr_holidays.hr_leave_view_tree_my",
                  form_view_ref: "hr_holidays.hr_leave_view_form",
              };

        openLeaveWindow(this.actionService, resModel, name, domain, context);
    }
}

export class TimeOffCard extends Component {
    static template = "hr_holidays.TimeOffCard";
    static props = {
        name: t.any(),
        data: t.any(),
        requires_allocation: t.any(),
        employeeId: t.any(),
        holidayStatusId: t.any(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.popover = usePopover(TimeOffCardPopover, {
            position: "bottom",
            class: "bg-view",
        });
        this.newAllocationRequest = useNewAllocationRequest();
        this.actionService = useService("action");
        this.lang = user.lang;
        this.formatNumber = formatNumber;
    }

    get warning() {
        return this.computeWarning().warning;
    }

    computeWarning() {
        const { data } = this.props;
        const excess = Object.values(data.virtual_excess_data);
        const errorLeaves = excess.map((entry) => entry.leave_id);
        const errorLeavesDuration = excess.reduce(
            (acc, entry) => acc + entry.amount,
            0,
        );
        const errorLeavesSignificant = data.allows_negative
            ? errorLeavesDuration > data.max_allowed_negative
            : errorLeavesDuration > 0;
        const accrualExcess = this.getAccrualExcess(data);
        const closeExpire =
            data.closest_allocation_duration &&
            data.closest_allocation_duration < data.virtual_remaining_leaves;
        return {
            errorLeaves,
            warning: errorLeavesSignificant || accrualExcess || closeExpire,
        };
    }

    onClickInfo(ev) {
        const { data, holidayStatusId, employeeId } = this.props;
        const { warning, errorLeaves } = this.computeWarning();
        this.popover.open(ev.target, {
            allocated: formatNumber(this.lang, data.max_leaves),
            accrual_bonus: formatNumber(this.lang, data.accrual_bonus),
            approved: formatNumber(this.lang, data.leaves_approved),
            planned: formatNumber(this.lang, data.leaves_requested),
            left: formatNumber(this.lang, data.virtual_remaining_leaves),
            warning,
            closest: data.closest_allocation_duration,
            request_unit: data.request_unit,
            exceeding_duration: data.exceeding_duration,
            allows_negative: data.allows_negative,
            max_allowed_negative: data.max_allowed_negative,
            onClickNewAllocationRequest: this.newAllocationRequestFrom.bind(this),
            errorLeaves,
            accrualExcess: this.getAccrualExcess(data),
            timeOffType: holidayStatusId,
            employeeId: employeeId,
            employeeCompany: data.employee_company,
        });
    }

    getAccrualExcess(data) {
        return data.allows_negative
            ? -data.exceeding_duration > data.max_allowed_negative
            : -data.exceeding_duration > 0;
    }

    async newAllocationRequestFrom() {
        this.popover.close();
        await this.newAllocationRequest(
            this.props.employeeId,
            this.props.holidayStatusId,
        );
    }

    async navigateTimeOffType() {
        const { employeeId, holidayStatusId, data } = this.props;
        const isInHolidaysUserGroup = await user.hasGroup(
            "hr_holidays.group_hr_holidays_user",
        );

        const resModel = "hr.leave";
        const name = _t("My Time Off");
        const domain = [
            ["holiday_status_id", "=", holidayStatusId],
            ["company_id", "=", data.employee_company],
            employeeId
                ? ["employee_id", "=", employeeId]
                : ["user_id", "=", user.userId],
        ];
        const context = isInHolidaysUserGroup
            ? {
                  search_default_group_date_from: true,
              }
            : {
                  list_view_ref: "hr_holidays.hr_leave_view_tree_my",
                  form_view_ref: "hr_holidays.hr_leave_view_form",
                  search_default_group_date_from: true,
              };

        openLeaveWindow(this.actionService, resModel, name, domain, context);
    }
}

function openLeaveWindow(actionService, resModel, name, domain, context) {
    actionService.doAction({
        type: "ir.actions.act_window",
        name: name,
        res_model: resModel,
        views: [
            [false, "list"],
            [false, "form"],
        ],
        domain: domain,
        context: context,
    });
}

export class TimeOffCardMobile extends TimeOffCard {
    static template = "hr_holidays.TimeOffCardMobile";
}
