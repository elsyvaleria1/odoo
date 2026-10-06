/** @odoo-module native */
import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { patch } from "@web/core/utils/patch";
import { MEDIAS_BREAKPOINTS, SIZES } from "@web/ui/viewport";

patch(activityGroupOpener, {
    open(context, group, ...rest) {
        const onMobile = window.innerWidth <= MEDIAS_BREAKPOINTS[SIZES.MD].minWidth;
        if (group.model === "hr.expense" && onMobile) {
            group = { ...group, view_type: "kanban" };
        }
        return super.open(context, group, ...rest);
    },
});
