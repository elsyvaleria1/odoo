/** @odoo-module native */
import { activityGroupOpener } from "@mail/core/web/activity_group_opener";
import { ActivityMenu } from "@mail/core/web/activity_menu";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { useCommand } from "@web/ui/commands";
import { FormViewDialog } from "@web/views/view_dialogs";

/** @type {WeakMap<object, Array<[number | false, string]>>} */
const todoViews = new WeakMap();

patch(ActivityMenu.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialogService = useService("dialog");
        useCommand(
            _t("Add a To-Do"),
            () => {
                document.body.click();
                this.createActivityTodo();
            },
            {
                category: "activity",
                hotkey: "alt+shift+t",
                global: true,
            },
        );
    },

    createActivityTodo() {
        this.dialogService.add(FormViewDialog, {
            title: _t("Add a To-Do"),
            resModel: "wizard.project.task.create.todo",
            preventCreate: true,
            size: "md",
        });
    },
});

patch(activityGroupOpener, {
    availableViews(context, group) {
        if (group.is_todo && todoViews.has(context.services)) {
            return todoViews.get(context.services);
        }
        return super.availableViews(...arguments);
    },

    async open(context, group) {
        if (group.is_todo && !todoViews.has(context.services)) {
            todoViews.set(
                context.services,
                await context.services.orm.call(
                    "project.task",
                    "get_todo_views_id",
                    [],
                ),
            );
        }
        return super.open(...arguments);
    },
});
