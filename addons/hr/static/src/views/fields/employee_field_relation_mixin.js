/** @odoo-module native */
import { AvatarCardEmployeePopover } from "@hr/components/avatar_card_employee/avatar_card_employee_popover";
import { onWillStart, t } from "@odoo/owl";
import { user } from "@web/core/user";
import { usePopover } from "@web/ui/popover";

/**
 * @template {typeof import("@odoo/owl").Component} T
 * @param {T} fieldClass
 */
export function EmployeeFieldRelationMixin(fieldClass) {
    return class extends fieldClass {
        static props = { ...fieldClass.props, relation: t.string().optional() };

        setup() {
            super.setup();
            onWillStart(async () => {
                this.isHrUser = await user.hasGroup("hr.group_hr_user");
            });
            this.avatarCard = usePopover(AvatarCardEmployeePopover, {
                closeOnClickAway: true,
            });
        }

        get relation() {
            if (this.props.relation) {
                return this.props.relation;
            }
            return "hr.employee";
        }

        getAvatarCardProps(record) {
            const originalProps = super.getAvatarCardProps(record);
            if (this.relation === "hr.employee") {
                return {
                    ...originalProps,
                    recordModel: this.relation,
                };
            }
            return originalProps;
        }
    };
}
