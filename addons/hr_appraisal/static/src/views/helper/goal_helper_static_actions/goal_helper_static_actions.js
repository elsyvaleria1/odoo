/** @odoo-module native */
import { _t } from "@web/core/translation";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";

export function getGoalStaticActionMenuItems(model, actionService) {
    const records = model.root.selection;
    return {
        save_as_template: {
            isAvailable: () => records.every((r) => !r.data.template_goal_id),
            sequence: 10,
            description: _t("Save as Template"),
            icon: "fa-regular fa-floppy-disk",
            callback: async () => {
                const action = await model.orm.call(
                    "hr.appraisal.goal",
                    "action_save_as_template",
                    [records.map((r) => r.resId)],
                );
                return actionService.doAction(action);
            },
            groupNumber: COG_GROUP.APP,
        },
        mark_as_done: {
            isAvailable: () => records.every((r) => r.data.progression !== "100"),
            sequence: 20,
            description: _t("Mark as Done"),
            icon: "fa-solid fa-check",
            callback: async () => {
                await model.orm.call("hr.appraisal.goal", "action_confirm", [
                    records.map((r) => r.resId),
                ]);
                await model.load();
            },
            groupNumber: COG_GROUP.APP,
        },
    };
}
