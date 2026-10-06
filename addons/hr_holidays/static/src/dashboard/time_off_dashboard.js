/** @odoo-module native */
import { useNewAllocationRequest } from "@hr_holidays/views/hooks";
import { useTimeOffContext } from "@hr_holidays/views/time_off_context";
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { DateTimeInput } from "@web/components/datetime";
import { serializeDate, today } from "@web/core/l10n/dates";
import { useBus, useService } from "@web/core/utils/hooks";

import { TimeOffCard } from "./time_off_card.js";

export class TimeOffDashboard extends Component {
    static components = { TimeOffCard, DateTimeInput };
    static template = "hr_holidays.TimeOffDashboard";
    static props = { employeeId: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.timeOffContext = useTimeOffContext();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.newRequest = useNewAllocationRequest();
        this.state = proxy({
            date: today(),
            today: today(),
            holidays: [],
            allocationRequests: 0,
        });
        useBus(this.timeOffContext.timeOffBus, "update_dashboard", async () => {
            await this.loadDashboardData();
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    getContext() {
        const context = {};
        if (this.props && this.props.employeeId !== null) {
            context["employee_id"] = this.props.employeeId;
        }
        return context;
    }

    async loadDashboardData(date = false) {
        const context = this.getContext();
        if (date) {
            this.state.date = date;
        }
        const dashboardData = await this.orm.call(
            "hr.employee",
            "get_time_off_dashboard_data",
            [serializeDate(this.state.date)],
            { context },
        );
        this.state.holidays = dashboardData["allocation_data"];
        this.state.allocationRequests = dashboardData["allocation_request_amount"];
        this.hasAccrualAllocation = dashboardData["has_accrual_allocation"];
    }

    async newAllocationRequest() {
        await this.newRequest(this.props.employeeId);
    }

    resetDate() {
        this.state.date = today();
        this.loadDashboardData();
    }

    async openPendingRequests() {
        if (!this.state.allocationRequests) {
            return;
        }
        const action = await this.orm.call(
            "hr.leave.allocation",
            "open_pending_requests",
            [],
            {
                context: this.getContext(),
            },
        );
        this.actionService.doAction(action);
    }
}
