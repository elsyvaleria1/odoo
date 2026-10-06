import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { patch } from "@web/core/utils/patch";

const KANBAN_ON_MOBILE = ["hr.leave", "hr.leave.allocation"];

patch(activityGroupOpener, {
    open(context, group, ...rest) {
        if (context.services.ui.isSmall && KANBAN_ON_MOBILE.includes(group.model)) {
            group = { ...group, view_type: "kanban" };
        }
        return super.open(context, group, ...rest);
    },
});
