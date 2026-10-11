/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { CalendarRenderer } from "@web/views/calendar";

import { TimeOffDashboard } from "../../dashboard/time_off_dashboard.js";
import { TimeOffCalendarCommonRenderer } from "./common/calendar_common_renderer.js";
import { TimeOffCalendarYearRenderer } from "./year/calendar_year_renderer.js";

export class TimeOffCalendarRenderer extends CalendarRenderer {
    static template = "hr_holidays.CalendarRenderer";
    static components = {
        ...TimeOffCalendarRenderer.components,
        day: TimeOffCalendarCommonRenderer,
        week: TimeOffCalendarCommonRenderer,
        month: TimeOffCalendarCommonRenderer,
        year: TimeOffCalendarYearRenderer,
        TimeOffDashboard,
    };
    get employeeId() {
        return this.props.model.employeeId;
    }

    get showDashboard() {
        return false;
    }
}

export class TimeOffDashboardCalendarRenderer extends TimeOffCalendarRenderer {
    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    get showDashboard() {
        const isManagementRelated =
            this.props?.model?.meta?.context?.is_management_related ?? false;
        return !this.ui.isSmall && !isManagementRelated;
    }
}
