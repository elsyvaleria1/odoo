/** @odoo-module native */

export function useTimesheetOvertimeProps(comp) {
    return {
        get props() {
            if (
                comp.resId &&
                comp.props.workingHours &&
                comp.resId in comp.props.workingHours
            ) {
                return comp.props.workingHours[comp.resId];
            } else {
                return {};
            }
        },
    };
}
