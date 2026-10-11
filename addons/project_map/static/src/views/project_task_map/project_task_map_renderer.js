/** @odoo-module native */
import { onWillStart } from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { MapRenderer } from "@web_map/map_view/map_renderer";

export class ProjectTaskMapRenderer extends MapRenderer {
    static template = "project_map.ProjectTaskMapRenderer";
    static subTemplates = {
        ...MapRenderer.subTemplates,
        PinListItems: "project_map.ProjectTaskMapRenderer.PinListItems",
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
        onWillStart(async () => {
            this.isProjectManager = await user.hasGroup(
                "project.group_project_manager",
            );
        });
    }

    getPinListItemClass(record) {
        const classes = super.getPinListItemClass(record);
        return record.date_start ? classes : `${classes} text-muted`;
    }

    get displayNoMapTokenAlert() {
        return super.displayNoMapTokenAlert && this.isProjectManager;
    }
}
