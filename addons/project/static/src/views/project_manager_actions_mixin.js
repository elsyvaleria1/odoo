/** @odoo-module native */
import { onWillStart } from "@odoo/owl";
import { user } from "@web/core/user";

const PROJECT_MANAGER_ACTIONS = ["duplicate", "archive", "unarchive"];

export const ProjectManagerActionsMixin = (T) =>
    class ProjectManagerActions extends T {
        setup() {
            super.setup(...arguments);
            this.isProjectManager = false;
            onWillStart(async () => {
                this.isProjectManager = await user.hasGroup(
                    "project.group_project_manager",
                );
            });
        }

        getStaticActionMenuItems() {
            const actionMenuItems = super.getStaticActionMenuItems(...arguments);
            if (!this.isProjectManager) {
                for (const item of PROJECT_MANAGER_ACTIONS) {
                    delete actionMenuItems[item];
                }
            }
            return actionMenuItems;
        }
    };
