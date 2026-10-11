/** @odoo-module native */
import { AvatarCardEmployeePopover } from "@hr/components/avatar_card_employee/avatar_card_employee_popover";
import { Avatar } from "@mail/views/web/fields/avatar/avatar";

export class GanttEmployeeAvatar extends Avatar {
    static template = "hr.GanttEmployeeAvatar";
    static components = { ...Avatar.components, Popover: AvatarCardEmployeePopover };

    get popoverProps() {
        return {
            id: this.props.resId,
            recordModel: this.props.resModel,
        };
    }
}
